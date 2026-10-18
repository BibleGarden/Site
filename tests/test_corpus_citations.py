"""Offline evidence tests: no network or real LLM calls."""

import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import yaml

from sitegen.content import parse_article
from sitegen.corpus import annotate, citations
from sitegen.errors import BuildError
from tools.check_corpus_citations import (CheckError, CorpusAPI, check_articles,
                                          command_judge, main, normalize, verify)

TEXT = 'First paragraph.\n\nPray with love and care.\n\nFinal paragraph.'
START = TEXT.index('Pray')
END = START + len('Pray with love and care.')
BOOK = dict(id=5, author='Author', title='Work', translator='Translator',
            source_url='https://predanie.ru/book', language='ru', license='public_domain')
ITEM = dict(id='prayer', chunk_id='book-5-1', book_id=5, char_start=START,
            char_end=END, text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
            kind='quote', text='Pray with love and care.', author='Author', title='Work',
            chapter='Prayer', translator='Translator', source_url=BOOK['source_url'])


class FakeCorpus:
    def __init__(self):
        self.hit = dict(chunk_id=ITEM['chunk_id'], book=copy.deepcopy(BOOK), chapter='Prayer',
                        char_start=START, char_end=END, text=TEXT[START:END],
                        text_sha256=ITEM['text_sha256'])
        self.book = dict(book=copy.deepcopy(BOOK), text=TEXT, text_sha256=ITEM['text_sha256'], sections=[])
        self.context = dict(book=copy.deepcopy(BOOK), text=TEXT, char_start=0,
                            char_end=len(TEXT), text_sha256=ITEM['text_sha256'])
        self.calls = []

    def request(self, path, data=None):
        self.calls.append((path, data))
        if path == '/search/chunks':
            return {'chunks': [self.hit]}
        if path == '/search/context':
            return self.context
        if path == '/books/5/text':
            return self.book
        raise AssertionError(path)


class CitationTest(unittest.TestCase):
    def setUp(self):
        self.item = copy.deepcopy(ITEM)
        self.api = FakeCorpus()

    def judge(self, payload):
        raise AssertionError('Quotes must not invoke an LLM')

    def test_exact_quote_and_canonical_range(self):
        self.assertTrue(verify(self.item, self.api, self.judge)[0])
        self.assertEqual(self.api.calls[-1][1]['scope'], 'leaf')

    def test_distorted_quote_fails(self):
        self.item['text'] = 'Pray without love and care.'
        self.assertFalse(verify(self.item, self.api, self.judge)[0])

    def test_quote_elsewhere_in_book_does_not_pass(self):
        self.item['text'] = 'Final paragraph.'
        self.api.context.update(text=TEXT[START:END], char_start=START, char_end=END)
        self.assertFalse(verify(self.item, self.api, self.judge, near=0)[0])

    def test_whitespace_quotes_and_nfc(self):
        self.assertEqual(normalize('«Cafe\u0301»\n\t ‘word’'), normalize('“Café”  ’word‘'))
        self.item['text'] = 'Pray\nwith   love and care.'
        self.assertTrue(verify(self.item, self.api, self.judge)[0])

    def test_stale_and_corrupt_hashes(self):
        for target in ('item', 'hit', 'book', 'context'):
            with self.subTest(target=target):
                api, item = FakeCorpus(), copy.deepcopy(ITEM)
                (item if target == 'item' else getattr(api, target))['text_sha256'] = '0' * 64
                with self.assertRaises(CheckError):
                    verify(item, api, self.judge)
        self.api.book['text'] += '!'
        with self.assertRaises(CheckError):
            verify(self.item, self.api, self.judge)

    def test_identity_metadata_chunk_range_and_context_fail_closed(self):
        mutations = [('hit', 'chunk_id', 'wrong'), ('hit', 'chapter', 'Wrong'),
                     ('hit', 'char_end', END-1), ('hit', 'text', 'wrong'),
                     ('context', 'text', 'wrong'), ('context', 'char_start', START+1)]
        for target, key, value in mutations:
            with self.subTest(target=target, key=key):
                api = FakeCorpus()
                getattr(api, target)[key] = value
                with self.assertRaises(CheckError):
                    verify(self.item, api, self.judge)
        for target in ('hit', 'book', 'context'):
            api = FakeCorpus()
            getattr(api, target)['book']['id'] = 8
            with self.assertRaises(CheckError):
                verify(self.item, api, self.judge)
        self.api.book['book']['translator'] = None
        with self.assertRaisesRegex(CheckError, 'translator'):
            verify(self.item, self.api, self.judge)

    def test_supported_and_wrong_meaning_retelling(self):
        self.item.update(kind='retelling', text='The author encourages loving prayer.')
        seen = []
        def judge(payload):
            seen.append(payload)
            return {'supported': True, 'reason': 'Supported by the fragment'}
        self.assertTrue(verify(self.item, self.api, judge)[0])
        self.assertEqual(seen[0]['source'], TEXT[START:END])
        self.item['text'] = 'The author says prayer is useless.'
        self.assertFalse(verify(self.item, self.api, lambda p: {'supported': False, 'reason': 'Contradiction'})[0])

    def test_missing_failed_and_malformed_judge(self):
        with self.assertRaises(CheckError):
            command_judge(None, {})
        for output in ('invalid', '{}', '{"supported":"yes","reason":"ok"}', '{"supported":true,"reason":""}'):
            with patch('tools.check_corpus_citations.subprocess.run') as run:
                run.return_value.stdout = output
                with self.assertRaises(CheckError):
                    command_judge('judge --json', {})
        with patch('tools.check_corpus_citations.subprocess.run') as run:
            run.return_value.stdout = '{"supported":false,"reason":"Unsupported"}'
            self.assertFalse(command_judge('judge --json', {})['supported'])
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_http_auth_and_409(self):
        with self.assertRaises(CheckError):
            CorpusAPI('http://fake', '')
        with patch('tools.check_corpus_citations.urlopen') as request:
            request.side_effect = HTTPError('http://fake', 409, 'stale', {}, None)
            with self.assertRaisesRegex(CheckError, '409.*refresh evidence'):
                CorpusAPI('http://fake', 'test-key').request('/search/chunks', {'ids': ['x']})
            self.assertEqual(request.call_args.args[0].get_header('X-api-key'), 'test-key')

    def body(self):
        return self.item['text'] + '[^corpus-prayer]\n'

    def test_schema_and_body_binding(self):
        self.assertEqual(citations([self.item], self.body(), 'test'), [self.item])
        for key, value in (('kind', 'summary'), ('char_start', True), ('char_end', -1),
                           ('book_id', 0), ('text_sha256', 'bad'), ('source_url', 'javascript:alert(1)'),
                           ('translator', ''), ('id', 'bad id')):
            with self.subTest(key=key):
                item = {**self.item, key: value}
                with self.assertRaises(BuildError):
                    citations([item], self.body(), 'test')
        for body in ('unrelated[^corpus-prayer]', self.body() * 2, self.body() + '[^corpus-missing]'):
            with self.assertRaises(BuildError):
                citations([self.item], body, 'test')
        with self.assertRaises(BuildError):
            citations([{**self.item, 'page': 3}], self.body(), 'test')

    def test_markers_in_code_and_comments_are_rejected(self):
        for body in ('```text\n' + self.body() + '```',
                     '`' + self.body().strip() + '`', '<!-- ' + self.body() + ' -->'):
            with self.subTest(body=body), self.assertRaises(BuildError):
                citations([self.item], body, 'test')

    def write_article(self, path, items):
        meta = dict(title='Fixture', description='Test only', date=date(2026, 10, 18), corpus_sources=items)
        path.write_text('---\n' + yaml.safe_dump(meta) + '---\n' + self.body(), encoding='utf-8')

    def test_sitegen_renders_translated_book_and_chapter_without_private_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ru.md'
            self.write_article(path, [self.item])
            article = parse_article(path, 'fixture', 'ru', {}, {}, {}, Path(tmp), site_key='lampada')
            self.assertIn('Author. Work. Prayer. перевод Translator', article.body_html)
            self.assertIn('href="https://predanie.ru/book"', article.body_html)
            self.assertIn('footnote-ref', article.body_html)
            self.assertNotIn(self.item['text_sha256'], article.body_html)
            self.assertNotIn(self.item['chunk_id'], article.body_html)
            self.assertNotIn('First paragraph.', article.body_html)

    def test_escaping_and_null_chapter_translator(self):
        item = {**self.item, 'author': '<Author>', 'chapter': None, 'translator': None}
        rendered = annotate(self.body(), [item], 'ru')
        self.assertIn('&lt;Author&gt;', rendered)
        self.assertNotIn('перевод', rendered)

    def test_report_continues_after_failure_and_has_article_beside_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.item['text'] = 'An invented quote.'
            self.write_article(path, [self.item])
            self.assertEqual(check_articles([path], self.api, self.judge, report), 1)
            result = report.read_text()
            self.assertIn('FAIL', result)
            self.assertIn('An invented quote.', result)
            self.assertIn('Pray with love and care.', result)
            self.item['text'] = ITEM['text']
            self.write_article(path, [self.item])
            self.assertEqual(check_articles([path], self.api, self.judge, report), 0)
            path.write_text('not front matter')
            self.assertEqual(check_articles([path], self.api, self.judge, report), 1)

    def test_cli_failure_and_success_with_fake_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.write_article(path, [self.item])
            with patch('tools.check_corpus_citations.CorpusAPI', return_value=self.api):
                self.assertEqual(main([str(path), '--report', str(report)]), 0)
                self.api.hit['text_sha256'] = '0' * 64
                self.assertEqual(main([str(path), '--report', str(report)]), 1)

    def test_judge_unavailable_preserves_source_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.item.update(kind='retelling', text='Prayer needs care.')
            self.write_article(path, [self.item])
            def judge(payload):
                raise CheckError('Judge unavailable')
            self.assertEqual(check_articles([path], self.api, judge, report), 1)
            self.assertIn('Judge unavailable', report.read_text())
            self.assertIn(TEXT[START:END], report.read_text())

    def test_report_on_stale_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.write_article(path, [self.item])
            self.api.hit['text_sha256'] = '0' * 64
            self.assertEqual(check_articles([path], self.api, self.judge, report), 1)
            self.assertIn('refresh evidence', report.read_text())


if __name__ == '__main__':
    unittest.main()
