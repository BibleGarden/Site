"""Private, content-addressed cache of complete editorial judge vote sets."""

import hashlib
import json
import os
from pathlib import Path
import tempfile

from tools.corpus_judge import CheckError, unique_object, validate_verdict


CACHE_VERSION = 1
DEFAULT_CACHE_DIR = Path.home() / '.cache/lampada-citation-judge'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


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
        self.hits += 1
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
