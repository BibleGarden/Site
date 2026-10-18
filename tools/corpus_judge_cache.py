"""Private, content-addressed cache of complete editorial judge vote sets."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import shlex
import shutil
import subprocess

from tools.corpus_judge import CheckError, unique_object, validate_verdict


CACHE_VERSION = 1
DEFAULT_CACHE_DIR = Path.home() / '.cache/lampada-citation-judge'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def judge_environment(command):
    """Identify the executable actually selected by PATH and the bundled CLI runtime."""
    try:
        arguments = shlex.split(command)
        executable = shutil.which(arguments[0]) if arguments else None
        if executable is None:
            raise CheckError('Judge adapter executable unavailable for cache identity')
        adapter = Path(executable).resolve()
        identity = {'adapter_sha256': hashlib.sha256(adapter.read_bytes()).hexdigest(),
                    'arguments': arguments[1:]}
        if adapter.name == 'corpus_judge_claude.sh':
            cli = shutil.which('claude')
            if cli is None:
                raise CheckError('Claude CLI unavailable for cache identity')
            result = subprocess.run([cli, '--version'], text=True, capture_output=True,
                                    timeout=10, check=True)
            if not result.stdout.strip():
                raise CheckError('Claude CLI returned an empty version')
            identity['claude_version'] = result.stdout.strip()
        return identity
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise CheckError('Cannot identify judge environment for cache; no fallback') from exc


class JudgeCache:
    def __init__(self, directory, identity):
        self.directory = Path(directory).expanduser().resolve()
        if self.directory.is_relative_to(Path(__file__).resolve().parents[1]):
            raise CheckError('Judge cache must be outside the repository')
        self.identity = identity
        self.hits = 0
        self.calls = 0

    def key(self, item, payload, runs):
        # IDs bind occurrences, but do not affect the judge's evidence or criteria.
        return digest({'version': CACHE_VERSION, 'identity': self.identity, 'runs': runs,
                       'item': {k: v for k, v in item.items() if k != 'id'}, 'payload': payload})

    def read(self, key, runs):
        path = self.directory / f'{key}.json'
        try:
            with path.open(encoding='utf-8') as stream:
                entry = json.load(stream, object_pairs_hook=unique_object)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, CheckError) as exc:
            raise CheckError(f'Cannot read judge cache entry {path}; remove or repair it explicitly') from exc
        try:
            if (not isinstance(entry, dict) or set(entry) != {'version', 'key', 'votes'}
                    or type(entry['version']) is not int or entry['version'] != CACHE_VERSION
                    or entry['key'] != key or not isinstance(entry['votes'], list)
                    or len(entry['votes']) != runs):
                raise CheckError('Invalid cache record')
            votes = [validate_verdict(vote) for vote in entry['votes']]
        except CheckError as exc:
            raise CheckError(f'Invalid judge cache entry {path}; remove or repair it explicitly') from exc
        return votes

    def write(self, key, votes):
        temporary = None
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                             prefix='.vote-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'version': CACHE_VERSION, 'key': key, 'votes': votes},
                          stream, ensure_ascii=False)
            os.replace(temporary, self.directory / f'{key}.json')
        except OSError as exc:
            raise CheckError(f'Cannot write judge cache {self.directory}') from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
