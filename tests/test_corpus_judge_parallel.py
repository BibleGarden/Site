"""Bounded judge concurrency with deterministic reports and complete error results."""

import threading
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_corpus_citations as fixtures
from tools.check_corpus_citations import CheckError, check_articles, main, verify
from tools.corpus_judge_cache import JudgeCache


class JudgeParallelTest(unittest.TestCase):
    def article(self, directory, count=4):
        items = [{**fixtures.ITEM, 'id': f'fragment-{i}', 'text': f'Claim {i}',
                  'kind': 'retelling', 'original': None, 'translation': None} for i in range(count)]
        fixture = fixtures.CitationTest()
        fixture.item = items[0]
        path = directory / 'ru.md'
        fixture.write_article(path, items)
        path.write_text(path.read_text().replace('[^corpus-prayer]', '[^corpus-fragment-0]') + '\n' + '\n'.join(
            item['text'] + f'[^corpus-{item["id"]}]' for item in items[1:]))
        return path, items

    def test_shared_limit_and_report_identical_to_sequential(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, _ = self.article(directory, 4)
            reports = []
            for workers in (1, 2, 6):
                lock = threading.Lock()
                active, peak, calls = 0, 0, 0
                active_fragments, overlap = {}, []
                # Force six jobs to coexist: three votes alone cannot pass this.
                barrier = threading.Barrier(6) if workers == 6 else None
                def judge(payload):
                    nonlocal active, peak, calls
                    claim = payload['article_text']
                    with lock:
                        active += 1
                        calls += 1
                        position = calls
                        peak = max(peak, active)
                        active_fragments[claim] = active_fragments.get(claim, 0) + 1
                        overlap.append(len(active_fragments))
                    try:
                        if barrier is not None and position <= 6:
                            barrier.wait(timeout=5)
                        # Complete later fragments sooner; report order must not follow completion.
                        time.sleep(0.008 * (4 - int(claim[-1])))
                        return {'verdict': 'PASS', 'category': 'supported', 'reason': claim}
                    finally:
                        with lock:
                            active -= 1
                            active_fragments[claim] -= 1
                            if not active_fragments[claim]:
                                del active_fragments[claim]
                report = directory / f'report-{workers}.md'
                self.assertEqual(check_articles([path], fixtures.FakeCorpus(), judge, report,
                                                 judge_name='fake', judge_workers=workers), 0)
                self.assertEqual(calls, 12)
                self.assertEqual(peak, workers)
                if workers == 6:
                    self.assertGreaterEqual(max(overlap), 2)
                reports.append(report.read_text())
            self.assertEqual(reports, [reports[0]] * 3)

    def test_error_waits_for_peers_and_other_fragments_and_never_caches_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, items = self.article(directory, 2)
            cache = JudgeCache(directory / 'cache', {'adapter': 'fake'})
            lock = threading.Lock()
            calls = {item['text']: 0 for item in items}
            completed = []
            def judge(payload):
                claim = payload['article_text']
                with lock:
                    calls[claim] += 1
                    run = calls[claim]
                if claim == 'Claim 0' and run == 1:
                    with lock:
                        completed.append('error')
                    raise CheckError('Unavailable')
                time.sleep(0.025)
                with lock:
                    completed.append(claim)
                return {'verdict': 'PASS', 'category': 'supported', 'reason': claim}
            report = directory / 'report.md'
            self.assertEqual(check_articles([path], fixtures.FakeCorpus(), judge, report,
                                             judge_name='fake', judge_cache=cache), 1)
            self.assertEqual(calls, {'Claim 0': 3, 'Claim 1': 3})
            self.assertEqual(len(completed), 6)
            text = report.read_text()
            self.assertEqual(text.count('Run '), 6)
            self.assertIn('Unavailable', text)
            self.assertIn('PASS: 1; FAIL: 0; UNSTABLE: 0; ERROR: 1', text)
            self.assertEqual(len(list(cache.directory.glob('*.json'))), 1)
            self.assertEqual(cache.calls, 6)
            self.assertEqual(cache.hits, 0)

    def test_invalid_limits_fail_explicitly(self):
        for workers in (0, -1, True, 1.5):
            with self.subTest(workers=workers), self.assertRaises(CheckError):
                verify(fixtures.ITEM, fixtures.FakeCorpus(), Mock(), judge_workers=workers)
        with tempfile.TemporaryDirectory() as tmp:
            for workers in ('0', '-1', 'invalid'):
                with self.subTest(workers=workers), self.assertRaises(SystemExit) as error:
                    main(['--report', str(Path(tmp) / 'r.md'), '--judge-workers', workers])
                self.assertEqual(error.exception.code, 2)

    def test_unexpected_judge_exception_propagates(self):
        item = {**fixtures.ITEM, 'kind': 'retelling', 'original': None, 'translation': None}
        with self.assertRaisesRegex(TypeError, 'programming defect'):
            verify(item, fixtures.FakeCorpus(), Mock(side_effect=TypeError('programming defect')))

    def test_all_articles_share_the_pool_without_article_barriers(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first, _ = self.article(directory, 1)
            second = directory / 'en.md'
            second.write_text(first.read_text().replace('Claim 0', 'Claim 1'))
            barrier = threading.Barrier(6)
            def judge(payload):
                barrier.wait(timeout=5)
                return {'verdict': 'PASS', 'category': 'supported', 'reason': payload['article_text']}
            report = directory / 'report.md'
            self.assertEqual(check_articles([first, second], fixtures.FakeCorpus(), judge, report,
                                             judge_name='fake', judge_workers=6), 0)
            self.assertLess(report.read_text().index(f'## {first}'), report.read_text().index(f'## {second}'))

    def test_duplicate_fragments_share_votes_with_or_without_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, _ = self.article(directory, 2)
            path.write_text(path.read_text().replace('Claim 1', 'Claim 0'))
            for cached in (False, True):
                judge = Mock(return_value={'verdict': 'PASS', 'category': 'supported', 'reason': 'Shared reason'})
                cache = JudgeCache(directory / 'cache', {}) if cached else None
                report = directory / f'report-{cached}.md'
                self.assertEqual(check_articles([path], fixtures.FakeCorpus(), judge, report,
                                                 judge_name='fake', judge_cache=cache), 0)
                self.assertEqual(judge.call_count, 3)
                self.assertEqual(report.read_text().count('Shared reason'), 6)
                if cached:
                    self.assertEqual(cache.calls, 3)
                    self.assertEqual(cache.hits, 1)
                    self.assertEqual(len(list(cache.directory.glob('*.json'))), 1)

    def test_cache_write_error_preserves_votes_and_source_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, _ = self.article(directory, 1)
            cache = JudgeCache(directory / 'cache', {})
            judge = Mock(return_value={'verdict': 'PASS', 'category': 'supported', 'reason': 'Concrete reason'})
            report = directory / 'report.md'
            with patch.object(cache, 'write', side_effect=CheckError('Disk full')) as write:
                self.assertEqual(check_articles([path], fixtures.FakeCorpus(), judge, report,
                                                 judge_name='fake', judge_cache=cache), 1)
                write.assert_called_once()
            text = report.read_text()
            self.assertIn('Cache write: ERROR — Disk full', text)
            self.assertEqual(text.count('Concrete reason'), 3)
            self.assertIn(fixtures.TEXT[fixtures.START:fixtures.END], text)
            self.assertIn('ERROR: 1', text)

    def test_unexpected_api_error_cancels_queued_votes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, _ = self.article(directory, 9)
            api = fixtures.FakeCorpus()
            request = api.request
            started = threading.Event()
            calls = []
            lookups = 0
            def broken_api(endpoint, data=None):
                nonlocal lookups
                if endpoint == '/search/chunks':
                    lookups += 1
                    if lookups == 2:
                        self.assertTrue(started.wait(timeout=5))
                        raise ConnectionResetError('API disconnected')
                return request(endpoint, data)
            def judge(payload):
                calls.append(payload['article_text'])
                started.set()
                time.sleep(0.05)
                return {'verdict': 'PASS', 'category': 'supported', 'reason': 'Concrete reason'}
            with patch.object(api, 'request', side_effect=broken_api):
                with self.assertRaisesRegex(ConnectionResetError, 'API disconnected'):
                    check_articles([path], api, judge, directory / 'report.md', judge_name='fake', judge_workers=1)
            self.assertEqual(calls, ['Claim 0'])
