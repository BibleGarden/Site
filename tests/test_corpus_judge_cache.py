"""Judge cache behavior with real checker flow and fake corpus/model."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_corpus_citations as fixtures
from tools.check_corpus_citations import CheckError, check_articles, main, verify
from tools.corpus_judge_cache import JudgeCache


PASS = {'verdict': 'PASS', 'category': 'supported', 'reason': 'Supported'}
FAIL = {'verdict': 'FAIL', 'category': 'addition', 'reason': 'Adds a claim'}


class JudgeCacheTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.cache = JudgeCache(self.directory / 'cache', {'model': 'opus', 'version': '1'})
        self.item = {**copy.deepcopy(fixtures.ITEM), 'kind': 'retelling', 'original': None,
                     'translation': None, 'text': 'Prayer needs care.'}
        self.api = fixtures.FakeCorpus()

    def test_second_article_run_has_no_judge_calls_and_one_edit_has_three(self):
        path, report = self.directory / 'ru.md', self.directory / 'report.md'
        second = {**self.item, 'id': 'second', 'text': 'Prayer should be loving.'}
        fixture = fixtures.CitationTest()
        fixture.item = self.item
        fixture.write_article(path, [self.item, second])
        path.write_text(path.read_text() + '\n' + second['text'] + '[^corpus-second]\n')
        judge = Mock(return_value=PASS)
        self.assertEqual(check_articles([path], self.api, judge, report, judge_name='fake', judge_cache=self.cache), 0)
        self.assertEqual(judge.call_count, 6)
        # A new cache instance proves persistence across checker processes.
        cache = JudgeCache(self.cache.directory, self.cache.identity)
        judge.reset_mock()
        self.assertEqual(check_articles([path], self.api, judge, report, judge_name='fake', judge_cache=cache), 0)
        judge.assert_not_called()
        self.assertEqual(report.read_text().count('Cache: HIT'), 2)
        self.assertIn('Judge calls: 0; cached fragments: 2', report.read_text())
        path.write_text(path.read_text().replace('Prayer needs care.', 'Prayer requires care.'))
        self.assertEqual(check_articles([path], self.api, judge, report, judge_name='fake', judge_cache=cache), 0)
        self.assertEqual(judge.call_count, 3)

    def test_key_covers_evidence_prompt_model_runs_and_adapter(self):
        payload = {'instruction': 'rubric', 'source': 'canonical range'}
        key = self.cache.key(self.item, payload, 3)
        mutations = {'text': 'Changed', 'kind': 'quote', 'original': 'Original',
                     'translation': 'ours', 'text_sha256': '0' * 64, 'char_start': 1,
                     'char_end': 3, 'book_id': 99, 'chunk_id': 'other', 'author': 'Other',
                     'title': 'Other work', 'chapter': 'Other chapter'}
        for field, value in mutations.items():
            with self.subTest(field=field):
                self.assertNotEqual(key, self.cache.key({**self.item, field: value}, payload, 3))
        for changed in ({**payload, 'instruction': 'new rubric'}, {**payload, 'source': 'new text'}):
            self.assertNotEqual(key, self.cache.key(self.item, changed, 3))
        self.assertNotEqual(key, self.cache.key(self.item, payload, 4))
        for identity in ({'model': 'sonnet', 'version': '1'}, {'model': 'opus', 'version': '2'}):
            self.assertNotEqual(key, JudgeCache(self.cache.directory, identity).key(self.item, payload, 3))
        self.assertEqual(key, self.cache.key({**self.item, 'id': 'other-occurrence'}, payload, 3))

    def test_prompt_or_model_change_really_calls_judge_again(self):
        judge = Mock(return_value=PASS)
        verify(self.item, self.api, judge, judge_cache=self.cache)
        self.assertEqual(judge.call_count, 3)
        with patch('tools.check_corpus_citations.JUDGE_INSTRUCTION', 'new rubric'):
            verify(self.item, self.api, judge, judge_cache=self.cache)
        self.assertEqual(judge.call_count, 6)
        other = JudgeCache(self.cache.directory, {'model': 'other', 'version': '1'})
        verify(self.item, self.api, judge, judge_cache=other)
        self.assertEqual(judge.call_count, 9)

    def test_complete_fail_and_unstable_are_reused(self):
        for votes, status in (([FAIL] * 3, 'FAIL'), ([PASS, FAIL, PASS], 'UNSTABLE')):
            with self.subTest(status=status):
                item = {**self.item, 'text': status}
                judge = Mock(side_effect=votes)
                first = verify(item, self.api, judge, judge_cache=self.cache)
                second = verify(item, self.api, judge, judge_cache=self.cache)
                self.assertEqual(first[0], status)
                self.assertEqual(second[0], status)
                self.assertEqual(judge.call_count, 3)
                self.assertIn('Cache: HIT', second[1])
                for vote in votes:
                    self.assertIn(vote['reason'], second[1])

    def test_error_is_not_cached_or_retried(self):
        judge = Mock(side_effect=[PASS, CheckError('Unavailable')])
        self.assertEqual(verify(self.item, self.api, judge, judge_cache=self.cache)[0], 'ERROR')
        self.assertEqual(judge.call_count, 2)
        self.assertEqual(list(self.cache.directory.glob('*.json')), [])
        next_judge = Mock(return_value=PASS)
        verify(self.item, self.api, next_judge, judge_cache=self.cache)
        self.assertEqual(next_judge.call_count, 3)

    def test_cache_does_not_skip_canonical_checks(self):
        judge = Mock(return_value=PASS)
        verify(self.item, self.api, judge, judge_cache=self.cache)
        self.api.hit['text_sha256'] = '0' * 64
        with self.assertRaises(CheckError):
            verify(self.item, self.api, judge, judge_cache=self.cache)
        self.assertEqual(judge.call_count, 3)

    def test_corruption_is_error_and_never_calls_judge(self):
        judge = Mock(return_value=PASS)
        verify(self.item, self.api, judge, judge_cache=self.cache)
        path = next(self.cache.directory.glob('*.json'))
        original = json.loads(path.read_text())
        corrupt = ['invalid', '{}', json.dumps({**original, 'votes': [PASS]}),
                   json.dumps({**original, 'key': 'wrong'}),
                   json.dumps({**original, 'votes': [{**PASS, 'verdict': 'ERROR'}] * 3}),
                   '{"version":1,"version":1,"key":"x","votes":[]}']
        for content in corrupt:
            with self.subTest(content=content):
                path.write_text(content)
                judge.reset_mock()
                with self.assertRaises(CheckError):
                    verify(self.item, self.api, judge, judge_cache=self.cache)
                judge.assert_not_called()

    def test_directory_errors_and_repository_path_are_explicit(self):
        with self.assertRaises(CheckError):
            JudgeCache(Path(__file__).resolve().parents[1] / 'cache', {})
        self.cache.directory.write_text('not a directory')
        with self.assertRaises(CheckError):
            verify(self.item, self.api, Mock(return_value=PASS), judge_cache=self.cache)

    def test_failed_atomic_write_is_explicit_and_cleans_temporary_file(self):
        with patch('tools.corpus_judge_cache.os.replace', side_effect=OSError('Disk full')):
            with self.assertRaisesRegex(CheckError, 'Cannot write judge cache'):
                verify(self.item, self.api, Mock(return_value=PASS), judge_cache=self.cache)
        self.assertEqual(list(self.cache.directory.iterdir()), [])

    def test_records_have_private_permissions_and_run_count_invalidates_votes(self):
        judge = Mock(return_value=PASS)
        verify(self.item, self.api, judge, judge_cache=self.cache)
        self.assertEqual(self.cache.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(next(self.cache.directory.glob('*.json')).stat().st_mode & 0o777, 0o600)
        verify(self.item, self.api, judge, judge_cache=self.cache, judge_runs=4)
        self.assertEqual(judge.call_count, 7)

    def test_cli_no_cache_reads_or_writes_nothing_and_passes_model(self):
        path, report = self.directory / 'ru.md', self.directory / 'report.md'
        fixture = fixtures.CitationTest()
        fixture.item = self.item
        fixture.write_article(path, [self.item])
        with patch('tools.check_corpus_citations.CorpusAPI', return_value=self.api), \
             patch('tools.check_corpus_citations.command_judge', return_value=PASS) as judge:
            args = [str(path), '--report', str(report), '--cache-dir', str(self.cache.directory)]
            self.assertEqual(main(args), 0)
            self.assertEqual(judge.call_count, 3)
            judge.reset_mock()
            self.assertEqual(main(args), 0)
            judge.assert_not_called()
            next(self.cache.directory.glob('*.json')).write_text('corrupt')
            self.assertEqual(main([*args, '--no-cache', '--judge-model', 'test-model']), 0)
            self.assertEqual(judge.call_count, 3)
            self.assertEqual(judge.call_args.args[2], 'test-model')
            self.assertIn('Judge cache: disabled', report.read_text())
            self.assertEqual(next(self.cache.directory.glob('*.json')).read_text(), 'corrupt')
