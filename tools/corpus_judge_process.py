"""Bounded judge workers with cancellation and owned process-group cleanup."""

from concurrent.futures import CancelledError, ThreadPoolExecutor
import os
import signal
import subprocess
import threading


_worker = threading.local()
CLEANUP_TIMEOUT = 5


class JudgeCleanupError(RuntimeError):
    pass


class JudgeProcesses:
    def __init__(self):
        self.lock = threading.Lock()
        self.stopped = False
        self.active = set()

    def start(self, command):
        with self.lock:
            if self.stopped:
                raise CancelledError()
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, start_new_session=True)
            self.active.add(process)
            return process

    @staticmethod
    def kill(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def stop(self):
        with self.lock:
            self.stopped = True
            for process in self.active:
                self.kill(process)

    def finish(self, process):
        # Kill the entire session group even if its leader has already exited.
        # communicate drains inherited pipes and reaps the leader before the slot
        # can run another adapter, including after timeout or interruption.
        self.kill(process)
        try:
            process.communicate(timeout=CLEANUP_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            self.stop()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            try:
                process.wait(timeout=CLEANUP_TIMEOUT)
            except subprocess.TimeoutExpired as wait_error:
                raise JudgeCleanupError('Judge process cleanup timed out; run aborted') from wait_error
            raise JudgeCleanupError('Judge process cleanup timed out; run aborted') from exc
        finally:
            with self.lock:
                self.active.discard(process)


def run_adapter(command, payload, *, timeout=120):
    processes = getattr(_worker, 'processes', None)
    if processes is None:
        processes = JudgeProcesses()
    process = processes.start(command)
    try:
        stdout, _ = process.communicate(payload, timeout=timeout)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
        return stdout
    finally:
        processes.finish(process)


class JudgeExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers):
        super().__init__(max_workers=max_workers)
        self.processes = JudgeProcesses()

    def submit(self, function, /, *args, **kwargs):
        def execute():
            with self.processes.lock:
                if self.processes.stopped:
                    raise CancelledError()
            _worker.processes = self.processes
            try:
                return function(*args, **kwargs)
            finally:
                del _worker.processes
        return super().submit(execute)

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.processes.stop()
        self.shutdown(wait=True, cancel_futures=exc_type is not None)
        return False
