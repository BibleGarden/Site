"""Offline publication registration tests; no live API calls."""

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from tools import register_corpus_usage as register
from tools.check_corpus_citations import CheckError, CorpusAPI
import test_corpus_citations as fixtures
from test_corpus_citations import FakeCorpus, ITEM, START, END


class RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = fixtures.CitationTest()
        self.fixture.item = copy.deepcopy(ITEM)
        self.api = FakeCorpus()
        self.api.hit['chunk_text_sha256'] = hashlib.sha256(self.api.hit['text'].encode()).hexdigest()
        self.existing = []
        self.writes = []
        original = self.api.request

        def request(path, data=None, *, method=None):
            if method:
                self.writes.append((method, path, data))
                if method == 'PUT':
                    return dict(source=path.removeprefix('/external-usage/').replace('%3A', ':'),
                                chunks=[dict(**chunk, stale=False) for chunk in data['chunks']])
                return None
            if path == '/external-usage':
                return self.existing
            return original(path, data)

        self.api.request = Mock(side_effect=request)

    def article(self, slug='prayer', language='ru', *, draft=False, items=None):
        path = self.root / slug / f'{language}.md'
        path.parent.mkdir(exist_ok=True)
        self.fixture.write_article(path, [self.fixture.item] if items is None else items)
        if items == []:
            path.write_text(path.read_text().replace(self.fixture.body(), 'No citations.'))
        if draft:
            path.write_text(path.read_text().replace('title: Fixture', 'draft: true\ntitle: Fixture'))
        return path

    def plan(self, slug=None):
        return register.plan(self.api, slug=slug, articles=self.root)

    def test_languages_share_one_source_and_exact_fragment_hash(self):
        for lang in ('ru', 'en', 'uk'):
            self.article(language=lang)
        operations = self.plan('prayer')
        self.assertEqual(operations, [('PUT', register.PREFIX + 'prayer', {'chunks': [
            {'chunk_id': ITEM['chunk_id'], 'text_sha256': self.api.hit['chunk_text_sha256']} ]})])
        self.assertNotEqual(operations[0][2]['chunks'][0]['text_sha256'], ITEM['text_sha256'])
        self.assertEqual(self.writes, [])
        with patch('sys.stdout', new=io.StringIO()):
            register.synchronize(self.api, operations)
        self.assertEqual(self.writes[0][1], '/external-usage/site%3Alampada/articles/prayer')
        self.assertEqual(sum(path == '/books/5/text' for path, _ in self.api.calls), 1)

    def test_union_of_different_language_chunks(self):
        self.article()
        self.fixture.item['chunk_id'] = 'book-5-2'
        self.article(language='en')
        original = self.api.request.side_effect
        def request(path, data=None, **kwargs):
            if path == '/search/chunks':
                hit = dict(self.api.hit, chunk_id=data['ids'][0])
                return {'chunks': [hit]}
            return original(path, data, **kwargs)
        self.api.request.side_effect = request
        self.assertEqual([c['chunk_id'] for c in self.plan('prayer')[0][2]['chunks']],
                         ['book-5-1', 'book-5-2'])

    def test_exact_utf8_fragment_hash_without_normalization_or_trimming(self):
        text = '  Моли\u0301сь\n\n'
        self.api.book.update(text=text, text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())
        self.api.hit.update(text=text, char_start=0, char_end=len(text),
                            text_sha256=self.api.book['text_sha256'])
        del self.api.hit['chunk_text_sha256']
        self.fixture.item.update(text='Моли\u0301сь', original='Моли\u0301сь', char_start=2,
                                 char_end=len(text) - 2, text_sha256=self.api.book['text_sha256'])
        self.article()
        self.assertEqual(self.plan('prayer')[0][2]['chunks'][0]['text_sha256'],
                         hashlib.sha256(text.encode('utf-8')).hexdigest())

    def test_sync_deletes_removed_and_draft_only_sources_preserves_other_namespaces(self):
        self.article()
        self.article('unpublished', draft=True)
        self.existing = [dict(source=source, chunks=[]) for source in (
            register.PREFIX + 'prayer', register.PREFIX + 'removed', register.PREFIX + 'unpublished',
            'post:4', 'site:other/articles/old', 'site:lampada/articles-other/prayer')]
        operations = self.plan()
        self.assertEqual([(method, source) for method, source, _ in operations], [
            ('PUT', register.PREFIX + 'prayer'), ('DELETE', register.PREFIX + 'removed'),
            ('DELETE', register.PREFIX + 'unpublished')])
        with patch('sys.stdout', new=io.StringIO()):
            register.synchronize(self.api, operations)
        self.assertEqual([op[0] for op in self.writes], ['PUT', 'DELETE', 'DELETE'])

    def test_drafts_skipped_and_no_sources_clears_old_usage(self):
        self.article(draft=True)
        self.assertEqual(self.plan('prayer'), [])
        self.article(language='en', items=[])
        self.assertEqual(self.plan('prayer'), [('PUT', register.PREFIX + 'prayer', {'chunks': []})])

    def test_dry_run_reads_but_never_writes(self):
        self.article()
        output = io.StringIO()
        with patch('sys.stdout', new=output):
            register.synchronize(self.api, self.plan(), dry_run=True)
        self.assertIn('PUT site:lampada/articles/prayer (1 chunks)', output.getvalue())
        self.assertEqual(self.writes, [])

    def test_all_preflight_finishes_before_any_mutation(self):
        self.article('a-valid')
        self.fixture.item['text_sha256'] = '0' * 64
        self.article('z-stale')
        with self.assertRaisesRegex(CheckError, 'z-stale.*reanchor'):
            self.plan()
        self.assertEqual(self.writes, [])

    def test_hash_identity_lookup_and_chunk_boundary_validation(self):
        self.article()
        mutations = [
            ('book', 'text', 'Changed book'), ('book', 'text_sha256', '0' * 64),
            ('hit', 'text_sha256', '0' * 64), ('hit', 'chunk_id', 'unknown'),
            ('hit', 'text', 'Wrong fragment'), ('hit', 'char_start', START + 1),
            ('hit', 'char_end', END - 1), ('hit', 'chunk_text_sha256', '0' * 64)]
        for target, key, value in mutations:
            with self.subTest(target=target, key=key):
                data = getattr(self.api, target)
                before = data[key]
                data[key] = value
                with self.assertRaises(CheckError):
                    self.plan('prayer')
                data[key] = before
        self.api.hit['book']['id'] = 9
        with self.assertRaisesRegex(CheckError, 'identity'):
            self.plan('prayer')
        self.assertEqual(self.writes, [])

    def test_missing_and_invalid_slug_fail(self):
        for slug in ('absent', '../escape', '.', '', 'UPPER'):
            with self.subTest(slug=slug), self.assertRaises(CheckError):
                self.plan(slug)

    def test_invalid_frontmatter_or_draft_fails_before_writes(self):
        path = self.article()
        path.write_text(path.read_text().replace('title: Fixture', 'draft: "false"\ntitle: Fixture'))
        with self.assertRaisesRegex(CheckError, 'draft must be a boolean'):
            self.plan()
        self.assertEqual(self.writes, [])

    def test_write_failure_stops_without_retry_or_delete(self):
        operations = [('PUT', register.PREFIX + 'prayer', {'chunks': []}),
                      ('DELETE', register.PREFIX + 'removed', None)]
        self.api.request.side_effect = CheckError('Corpus HTTP 409')
        with patch('sys.stdout', new=io.StringIO()), self.assertRaisesRegex(CheckError, '409.*No retry'):
            register.synchronize(self.api, operations)
        self.api.request.assert_called_once()

    def test_conflicting_hashes_across_languages_abort_preflight(self):
        self.article()
        self.article(language='en')
        with patch.object(register, 'fragment_hash', side_effect=['a' * 64, 'b' * 64]):
            with self.assertRaisesRegex(CheckError, 'conflicting fragment hashes'):
                self.plan()
        self.assertEqual(self.writes, [])

    def test_changed_file_during_preflight_aborts(self):
        path = self.article()
        def changed(*args):
            path.write_text(path.read_text() + '\nChanged')
            return 'a' * 64
        with patch.object(register, 'fragment_hash', side_effect=changed):
            with self.assertRaisesRegex(CheckError, 'changed during preflight'):
                self.plan()
        self.assertEqual(self.writes, [])

    def test_cli_environment_and_no_writes_on_dry_run(self):
        self.article()
        with patch.dict(os.environ, {'CORPUS_API_KEY': 'private', 'CORPUS_API_URL': 'http://fake'}), \
                patch.object(register, 'CorpusAPI', return_value=self.api) as factory, \
                patch.object(register, 'plan', return_value=[]) as planner:
            self.assertEqual(register.main(['--slug', 'prayer', '--dry-run']), 0)
            factory.assert_called_once_with('http://fake', 'private')
            planner.assert_called_once_with(self.api, slug='prayer')
        with patch.dict(os.environ, {}, clear=True), patch('sys.stderr', new=io.StringIO()) as errors:
            self.assertEqual(register.main(['--all']), 1)
            self.assertIn('CORPUS_API_KEY is required', errors.getvalue())


class UsageClientTest(unittest.TestCase):
    def setUp(self):
        self.api = CorpusAPI('http://fake', 'private')
        self.entry = dict(source=register.PREFIX + 'prayer', chunks=[dict(
            chunk_id='book-5-1', text_sha256='a' * 64, stale=False)])

    @patch('tools.check_corpus_citations.urlopen')
    def test_put_get_and_empty_delete(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(self.entry).encode()
        body = {'chunks': [{k: v for k, v in self.entry['chunks'][0].items() if k != 'stale'}]}
        self.assertEqual(self.api.request('/external-usage/site%3Alampada/articles/prayer',
                                          body, method='PUT'), self.entry)
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_method(), 'PUT')
        self.assertEqual(req.full_url,
                         'http://fake/api/v1/channels/lampada/external-usage/site%3Alampada/articles/prayer')
        self.assertEqual(json.loads(req.data), body)
        self.assertEqual(req.get_header('X-api-key'), 'private')
        response.read.return_value = json.dumps([self.entry]).encode()
        self.assertEqual(self.api.request('/external-usage'), [self.entry])
        response.status = 204
        response.read.side_effect = AssertionError('204 must not parse JSON')
        self.assertIsNone(self.api.request('/external-usage/site%3Alampada/articles/prayer', method='DELETE'))
        self.assertEqual(urlopen.call_args.args[0].get_method(), 'DELETE')

    def test_malformed_responses_fail(self):
        for value in ({}, [dict(source='site:foo')], [dict(source='site:foo', chunks=[{}])],
                      [dict(source='site:lampada//bad', chunks=[])],
                      [self.entry, self.entry]):
            with self.subTest(value=value), self.assertRaises(CheckError):
                self.api.validate_response('/external-usage', value)

    @patch('tools.check_corpus_citations.urlopen')
    def test_api_errors_and_invalid_json_fail_without_retry(self, urlopen):
        for code in (401, 404, 409, 422, 500):
            urlopen.reset_mock()
            urlopen.side_effect = HTTPError('http://fake', code, 'failure', {}, None)
            with self.subTest(code=code), self.assertRaisesRegex(CheckError, f'HTTP {code}'):
                self.api.request('/external-usage/site%3Alampada/articles/prayer', {'chunks': []}, method='PUT')
            urlopen.assert_called_once()
        urlopen.side_effect = URLError('offline')
        with self.assertRaises(CheckError):
            self.api.request('/external-usage')
        urlopen.side_effect = None
        urlopen.return_value.__enter__.return_value.read.return_value = b'not JSON'
        with self.assertRaises(CheckError):
            self.api.request('/external-usage')


if __name__ == '__main__':
    unittest.main()
