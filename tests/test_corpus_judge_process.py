"""Real adapter descendants must not outlive a timeout, slot or cancellation."""

import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from unittest.mock import Mock, patch

import test_corpus_citations as fixtures
from tools.corpus_judge_process import JudgeCleanupError, JudgeExecutor, JudgeProcesses, run_adapter


class JudgeProcessTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.addCleanup(self.kill_groups)
        self.adapter = self.root / 'adapter.py'
        child = "import os, pathlib, sys, time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)"
        self.adapter.write_text(
            'import os, pathlib, subprocess, sys, time\n'
            'root = pathlib.Path(sys.argv[1])\n'
            'pid = os.getpid()\n'
            '(root / f"parent-{pid}").write_text(str(pid))\n'
            f'subprocess.Popen([sys.executable, "-c", {child!r}, str(root / f"child-{{pid}}")])\n'
            'time.sleep(30)\n')
        self.command = [sys.executable, str(self.adapter), str(self.root)]

    def kill_groups(self):
        for marker in self.root.glob('parent-*'):
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def alive(self, pid):
        try:
            state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
            return state != 'Z'
        except (FileNotFoundError, ProcessLookupError):
            return False

    def pids(self):
        return [int(p.read_text()) for pattern in ('parent-*', 'child-*') for p in self.root.glob(pattern)]

    def ready(self):
        markers = list(self.root.glob('child-*'))
        return bool(markers) and all(marker.read_text().strip() for marker in markers)

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition():
            if time.monotonic() >= deadline:
                self.fail('Fixture adapter did not start')
            time.sleep(0.01)

    def test_timeout_kills_descendants_before_the_next_slot(self):
        with JudgeExecutor(max_workers=1) as executor:
            first = executor.submit(run_adapter, self.command, '{}', timeout=0.4)
            self.wait_for(self.ready)
            observed_pids = self.pids()
            next_slot = executor.submit(lambda: [pid for pid in observed_pids if self.alive(pid)])
            with self.assertRaises(subprocess.TimeoutExpired):
                first.result(timeout=5)
            self.assertEqual(next_slot.result(timeout=5), [])
        self.assertEqual(len(list(self.root.glob('parent-*'))), 1)
        self.assertFalse(any(self.alive(pid) for pid in observed_pids))

    def test_sigint_cancels_queue_and_kills_active_adapter_group(self):
        root = Path(__file__).resolve().parents[1]
        harness = self.root / 'interrupt.py'
        harness.write_text(
            'import sys\n'
            f'sys.path[:0] = [{str(root)!r}, {str(root / "tests")!r}]\n'
            'from functools import partial\n'
            'from tools.check_corpus_citations import command_judge, verify\n'
            'from test_corpus_citations import ITEM, FakeCorpus\n'
            'item = {**ITEM, "kind":"retelling", "original":None, "translation":None, "text":"Claim"}\n'
            'try:\n'
            f'    verify(item, FakeCorpus(), partial(command_judge, {shlex.join(self.command)!r}), judge_runs=27, judge_workers=1)\n'
            'except KeyboardInterrupt:\n'
            '    sys.exit(130)\n')
        process = subprocess.Popen([sys.executable, str(harness)], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(self.ready)
            pids = self.pids()
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 130, stdout + stderr)
            self.assertEqual(len(list(self.root.glob('parent-*'))), 1)
            self.assertFalse(any(self.alive(pid) for pid in pids))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_normal_reply_and_nonzero_exit_are_preserved(self):
        output = run_adapter([sys.executable, '-c', 'import sys; print(sys.stdin.read())'], 'payload')
        self.assertEqual(output.strip(), 'payload')
        with self.assertRaises(subprocess.CalledProcessError) as error:
            run_adapter([sys.executable, '-c', 'raise SystemExit(7)'], '{}')
        self.assertEqual(error.exception.returncode, 7)

    def assert_main_signal_cancellation(self, signum):
        root = Path(__file__).resolve().parents[1]
        item = {**fixtures.ITEM, 'kind': 'retelling', 'original': None, 'translation': None, 'text': 'Claim'}
        fixture = fixtures.CitationTest()
        fixture.item = item
        article = self.root / 'article.md'
        fixture.write_article(article, [item])
        arguments = [str(article), '--no-cache', '--report', str(self.root / 'report.md'),
                     '--judge-command', shlex.join(self.command), '--judge-runs', '27', '--judge-workers', '1']
        harness = self.root / 'signal-main.py'
        harness.write_text(
            'import sys\n'
            f'sys.path[:0] = [{str(root)!r}, {str(root / "tests")!r}]\n'
            'from tools import check_corpus_citations as checker\n'
            'from test_corpus_citations import FakeCorpus\n'
            'checker.CorpusAPI = lambda *args: FakeCorpus()\n'
            'try:\n'
            f'    sys.exit(checker.main({arguments!r}))\n'
            'except KeyboardInterrupt:\n'
            '    sys.exit(130)\n')
        process = subprocess.Popen([sys.executable, str(harness)], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(self.ready)
            pids = self.pids()
            process.send_signal(signum)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 130, stdout + stderr)
            self.assertEqual(len(list(self.root.glob('parent-*'))), 1)
            self.assertFalse(any(self.alive(pid) for pid in pids))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_sigterm_in_main_cancels_queue_and_process_groups(self):
        self.assert_main_signal_cancellation(signal.SIGTERM)

    def test_sighup_in_main_cancels_queue_and_process_groups(self):
        self.assert_main_signal_cancellation(signal.SIGHUP)

    def test_cleanup_communicate_is_bounded_and_failure_stops_run(self):
        processes = JudgeProcesses()
        process = Mock()
        processes.active.add(process)
        process.communicate.side_effect = subprocess.TimeoutExpired('adapter', 5)
        with patch.object(processes, 'kill'):
            with self.assertRaisesRegex(JudgeCleanupError, 'cleanup timed out'):
                processes.finish(process)
        process.communicate.assert_called_once_with(timeout=5)
        process.wait.assert_called_once_with(timeout=5)
        self.assertTrue(processes.stopped)
        self.assertEqual(processes.active, set())
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close.assert_called_once()
