"""Offline evidence tests: no network or real LLM calls."""

import copy
from datetime import date
import hashlib
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import yaml

from sitegen.content import parse_article
from sitegen.corpus import annotate, citations
from sitegen.errors import BuildError
from tools.check_corpus_citations import (CheckError, CorpusAPI, DEFAULT_JUDGE, check_articles,
                                          command_judge, main, normalize, validate_verdict, verify)

TEXT = 'First paragraph.\n\nPray with love and care.\n\nFinal paragraph.'
START = TEXT.index('Pray')
END = START + len('Pray with love and care.')
BOOK = dict(id=5, author='Author', title='Work', translator='Translator',
            source_url='https://predanie.ru/book', language='ru', license='public_domain')
ITEM = dict(id='prayer', chunk_id='book-5-1', book_id=5, char_start=START,
            char_end=END, text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
            kind='quote', text='Pray with love and care.', original='Pray with love and care.',
            translation='published', author='Author', title='Work',
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
        self.assertEqual(verify(self.item, self.api, self.judge)[0], "PASS")
        self.assertEqual(self.api.calls[-1][1]['scope'], 'leaf')

    def test_distorted_quote_fails(self):
        self.item['text'] = 'Pray without love and care.'
        self.assertEqual(verify(self.item, self.api, self.judge)[0], "FAIL")

    def test_quote_elsewhere_in_book_does_not_pass(self):
        self.item.update(text='Final paragraph.', original='Final paragraph.')
        # Full report context contains the quote, but the precise range does not.
        self.assertEqual(verify(self.item, self.api, self.judge)[0], "FAIL")

    def test_whitespace_quotes_and_nfc(self):
        self.assertEqual(normalize('«Cafe\u0301»\n\t ‘word’'), normalize('“Café”  ’word‘'))
        self.item['text'] = 'Pray\nwith   love and care.'
        self.assertEqual(verify(self.item, self.api, self.judge)[0], "PASS")

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
        self.item.update(kind='retelling', original=None, translation=None, text='Prayer should be loving.')
        seen = []
        def judge(payload):
            seen.append(payload)
            return {'verdict': 'PASS', 'category': 'supported', 'reason': 'Supported by the fragment'}
        self.assertEqual(verify(self.item, self.api, judge)[0], "PASS")
        self.assertEqual(seen[0]['source'], TEXT[START:END])
        self.item['text'] = 'Prayer is useless.'
        self.assertEqual(verify(self.item, self.api, lambda p: {'verdict': 'FAIL', 'category': 'contradiction', 'reason': 'Contradiction'})[0], "FAIL")

    def test_missing_failed_and_malformed_judge(self):
        with self.assertRaises(CheckError):
            command_judge(None, {})
        for output in ('invalid', '{}', '{"supported":"yes","reason":"ok"}', '{"supported":true,"reason":""}'):
            with patch('tools.check_corpus_citations.subprocess.run') as run:
                run.return_value.stdout = output
                with self.assertRaises(CheckError):
                    command_judge('judge --json', {})
        with patch('tools.check_corpus_citations.subprocess.run') as run:
            run.return_value.stdout = '{"verdict":"FAIL","category":"contradiction","reason":"Unsupported"}'
            self.assertEqual(command_judge('judge --json', {})['verdict'], 'FAIL')
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_adapter_failures_are_explicit_without_retry(self):
        for error in (OSError('Unavailable'), subprocess.TimeoutExpired('judge', 120),
                      subprocess.CalledProcessError(1, 'judge')):
            with self.subTest(error=type(error).__name__), \
                 patch('tools.check_corpus_citations.subprocess.run', side_effect=error) as run:
                with self.assertRaises(CheckError):
                    command_judge('judge --json', {})
                self.assertEqual(run.call_count, 1)

    def test_independent_runs_consensus_and_disagreement(self):
        self.item.update(kind='retelling', original=None, translation=None, text='Prayer needs care.')
        passed = {'verdict': 'PASS', 'category': 'secondary_omission', 'reason': 'Meaning unchanged'}
        failed = {'verdict': 'FAIL', 'category': 'meaning_changing_omission',
                  'reason': 'Omitting care makes the instruction unconditional'}
        for answers, expected in (([passed] * 3, 'PASS'), ([failed] * 3, 'FAIL'),
                                  ([passed, failed, passed], 'UNSTABLE'),
                                  ([failed, failed, passed], 'UNSTABLE')):
            with self.subTest(expected=expected):
                judge = Mock(side_effect=answers)
                status, reason, _ = verify(self.item, self.api, judge)
                self.assertEqual(status, expected)
                self.assertEqual(judge.call_count, 3)
                for number, answer in enumerate(answers, 1):
                    self.assertIn(f'Run {number}/3: {answer["verdict"]} [{answer["category"]}]', reason)
                    self.assertIn(answer['reason'], reason)
                payloads = [call.args[0] for call in judge.call_args_list]
                self.assertEqual(payloads, [payloads[0]] * 3)
                self.assertIsNot(payloads[0], payloads[1])

    def test_judge_errors_stop_without_retry_and_keep_previous_reason(self):
        self.item.update(kind='retelling', original=None, translation=None, text='Prayer needs care.')
        passed = {'verdict': 'PASS', 'category': 'supported', 'reason': 'First explanation'}
        for error in (CheckError('Unavailable'), {}, {'verdict': 'PASS'}):
            judge = Mock(side_effect=[passed, error, passed])
            status, reason, paragraph = verify(self.item, self.api, judge)
            self.assertEqual(status, 'ERROR')
            self.assertEqual(judge.call_count, 2)
            self.assertIn('First explanation', reason)
            self.assertIn('Run 2/3: ERROR', reason)
            self.assertIn(TEXT[START:END], paragraph)

    def test_strict_verdict_schema(self):
        valid = {'verdict': 'PASS', 'category': 'supported', 'reason': 'Evidence agrees'}
        invalid = [None, [], True, {**valid, 'extra': 1}]
        for key, values in {'verdict': ['pass', True, None, []],
                            'category': ['unknown', 'distortion', None, []],
                            'reason': ['', '  ', 1, None]}.items():
            invalid.extend({**valid, key: value} for value in values)
        invalid.append({'verdict': 'FAIL', 'category': 'supported', 'reason': 'Mismatch'})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(CheckError):
                validate_verdict(value)

    def test_configurable_runs_and_invalid_counts(self):
        self.item.update(kind='retelling', original=None, translation=None, text='Prayer needs care.')
        judge = Mock(return_value={'verdict': 'PASS', 'category': 'supported', 'reason': 'Supported'})
        self.assertEqual(verify(self.item, self.api, judge, judge_runs=4)[0], 'PASS')
        self.assertEqual(judge.call_count, 4)
        for runs in (0, -1, True, 1.5):
            with self.subTest(runs=runs), self.assertRaises(CheckError):
                verify(self.item, self.api, judge, judge_runs=runs)
        with tempfile.TemporaryDirectory() as tmp:
            for runs in ('0', '-1', 'bad'):
                with self.subTest(runs=runs), self.assertRaises(SystemExit) as error:
                    main(['--report', str(Path(tmp) / 'review.md'), '--judge-runs', runs])
                self.assertEqual(error.exception.code, 2)

    def test_unstable_report_preserves_all_reasons_and_fails(self):
        self.item.update(kind='retelling', original=None, translation=None, text='Prayer needs care.')
        judge = Mock(side_effect=[
            {'verdict': 'PASS', 'category': 'supported', 'reason': 'First reason'},
            {'verdict': 'FAIL', 'category': 'addition', 'reason': 'Second reason'},
            {'verdict': 'PASS', 'category': 'secondary_omission', 'reason': 'Third reason'}])
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.write_article(path, [self.item])
            self.assertEqual(check_articles([path], self.api, judge, report, judge_name='stub'), 1)
            result = report.read_text()
            self.assertIn('| prayer | retelling | UNSTABLE |', result)
            self.assertIn('Verdict: UNSTABLE', result)
            for reason in ('First reason', 'Second reason', 'Third reason'):
                self.assertIn(reason, result)

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
            self.assertIn('Author. Work. Prayer, перевод Translator', article.body_html)
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
            self.item.update(kind='retelling', original=None, translation=None, text='Prayer needs care.')
            self.write_article(path, [self.item])
            def judge(payload):
                raise CheckError('Judge unavailable')
            self.assertEqual(check_articles([path], self.api, judge, report), 1)
            self.assertIn('Judge unavailable', report.read_text())
            self.assertIn('Verdict: ERROR', report.read_text())
            self.assertIn(TEXT[START:END], report.read_text())

    def test_translated_quote_judges_article_against_verbatim_original(self):
        self.item.update(text='Молитесь с любовью и заботой.', translation='ours')
        seen = []
        def judge(payload):
            seen.append(payload)
            return {'verdict': 'PASS', 'category': 'supported', 'reason': 'Faithful translation'}
        self.assertEqual(verify(self.item, self.api, judge)[0], "PASS")
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[0]['original'], ITEM['original'])
        self.assertEqual(seen[0]['source'], ITEM['original'])
        self.assertEqual(seen[0]['article_text'], self.item['text'])
        self.assertEqual(seen[0]['kind'], 'translation')
        self.assertNotIn('source_context', seen[0])
        self.assertIn('Natural idiomatic translation', seen[0]['instruction'])
        self.assertEqual(verify(self.item, self.api, lambda p: {'verdict': 'FAIL', 'category': 'addition', 'reason': 'Added claim'})[0], "FAIL")
        self.item['original'] = 'Pray without love and care.'
        self.assertEqual(verify(self.item, self.api, self.judge)[0], "FAIL")

    def test_untranslated_and_published_quotes_cannot_bypass_verbatim_text(self):
        for mode in (None, 'published'):
            self.item['translation'] = mode
            self.assertEqual(verify(self.item, self.api, self.judge)[0], "PASS")
            self.item['text'] = 'Our changed wording.'
            self.assertEqual(verify(self.item, self.api, self.judge)[0], "FAIL")
            self.item['text'] = ITEM['text']
        for original in ('Pray … care.', 'Pray with care.', 'Pray with love and hate.'):
            self.item.update(original=original, text=original)
            self.assertEqual(verify(self.item, self.api, self.judge)[0], "FAIL")

    def test_translation_schema(self):
        for updates in ({'original': None}, {'original': ''}, {'translation': 'unknown'},
                        {'translation': 'published', 'translator': None},
                        {'kind': 'retelling', 'original': None, 'translation': 'ours'},
                        {'kind': 'retelling', 'translation': None}):
            with self.subTest(updates=updates), self.assertRaises(BuildError):
                citations([{**self.item, **updates}], self.body(), 'test')
        item = {**self.item, 'translation': 'ours', 'translator': None}
        self.assertEqual(citations([item], self.body(), 'test'), [item])
        for missing in ('original', 'translation'):
            item = copy.deepcopy(self.item)
            del item[missing]
            with self.assertRaises(BuildError):
                citations([item], self.body(), 'test')

    def test_our_translation_footnotes_in_all_languages_and_edition_translator(self):
        self.item['translation'] = 'ours'
        for lang, label in (('en', 'our translation'), ('ru', 'наш перевод'), ('uk', 'наш переклад')):
            with self.subTest(lang=lang):
                rendered = annotate(self.body(), [self.item], lang)
                self.assertIn(', ' + label, rendered)
                self.assertIn('Translator', rendered)
        self.item['translator'] = None
        self.assertNotIn('Translator', annotate(self.body(), [self.item], 'en'))
        self.item.update(translation='published', translator='Published Name')
        self.assertIn(', translated by Published Name', annotate(self.body(), [self.item], 'en'))
        self.assertNotIn('our translation', annotate(self.body(), [self.item], 'en'))

    def test_closing_quotes_and_punctuation_between_text_and_marker(self):
        for ending in ('»', '”.', '»; ', '\"!', '’?', ').', '…'):
            with self.subTest(ending=ending):
                body = '«' + self.item['text'] + ending + '[^corpus-prayer]'
                self.assertEqual(citations([self.item], body, 'test'), [self.item])
        with self.assertRaises(BuildError):
            citations([self.item], self.item['text'] + ' unrelated [^corpus-prayer]', 'test')

    def test_source_translator_uses_comma_in_all_languages(self):
        for lang, label in (('en', 'translated by'), ('ru', 'перевод'), ('uk', 'переклад')):
            with self.subTest(lang=lang):
                rendered = annotate(self.body(), [self.item], lang)
                self.assertIn(f'Prayer, {label} Translator', rendered)
                self.assertNotIn(f'Prayer. {label}', rendered)

    def test_translated_quote_build_with_wrapping_punctuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ru.md'
            self.item.update(text='Молитесь с любовью и заботой.', translation='ours')
            self.write_article(path, [self.item])
            source = path.read_text()
            source = source.replace(self.body(), '«' + self.item['text'] + '».[^corpus-prayer]')
            path.write_text(source)
            article = parse_article(path, 'fixture', 'ru', {}, {}, {}, Path(tmp), site_key='lampada')
            self.assertIn('наш перевод', article.body_html)
            self.assertNotIn(ITEM['original'], article.body_html)
            self.assertIn('footnote-ref', article.body_html)

    def test_bible_garden_rejects_corpus_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'en.md'
            self.write_article(path, [self.item])
            with self.assertRaisesRegex(BuildError, 'unknown frontmatter.*corpus_sources'):
                parse_article(path, 'fixture', 'en', {}, {}, {}, Path(tmp), site_key='bible-garden')

    def test_full_book_cached_by_book_id_and_hash_but_chunks_remain_current(self):
        cache = {}
        for _ in range(2):
            self.assertEqual(verify(self.item, self.api, self.judge, book_cache=cache)[0], "PASS")
        self.assertEqual(sum(path == '/books/5/text' for path, data in self.api.calls), 1)
        self.assertEqual(sum(path == '/search/chunks' for path, data in self.api.calls), 2)
        self.api.hit['text_sha256'] = '0' * 64
        with self.assertRaisesRegex(CheckError, 'refresh evidence'):
            verify(self.item, self.api, self.judge, book_cache=cache)
        new_text = TEXT + ' New paragraph.'
        new_hash = hashlib.sha256(new_text.encode()).hexdigest()
        self.api.book.update(text=new_text, text_sha256=new_hash)
        self.api.hit['text_sha256'] = new_hash
        self.api.context.update(text=new_text, char_end=len(new_text), text_sha256=new_hash)
        self.item['text_sha256'] = new_hash
        self.assertEqual(verify(self.item, self.api, self.judge, book_cache=cache)[0], "PASS")
        self.assertEqual(sum(path == '/books/5/text' for path, data in self.api.calls), 2)
        self.assertEqual(set(cache), {(5, ITEM['text_sha256']), (5, new_hash)})

    def test_summary_table_precedes_details_with_explicit_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.write_article(path, [self.item])
            self.assertEqual(check_articles([path], self.api, self.judge, report), 0)
            result = report.read_text()
            self.assertLess(result.index('| Article | Citation | Kind | Verdict |'), result.index('## '))
            self.assertIn('| prayer | quote | PASS |', result)
            self.assertIn('Verdict: PASS', result)
            self.assertIn('Original quotation:', result)
            self.assertIn('Judge command/adapter', result)
            self.assertIn('CitationTest.judge', result)

    def test_cli_uses_default_adapter_and_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.item.update(translation='ours', text='Молитесь с любовью и заботой.')
            self.write_article(path, [self.item])
            for command, runs in ((None, 3), ('custom-judge --json', 4)):
                with patch.dict(os.environ):
                    os.environ.pop('CORPUS_JUDGE_COMMAND', None)
                    if command is not None:
                        os.environ['CORPUS_JUDGE_COMMAND'] = command
                    with patch('tools.check_corpus_citations.CorpusAPI', return_value=self.api), \
                         patch('tools.check_corpus_citations.command_judge') as judge:
                        judge.return_value = {'verdict': 'PASS', 'category': 'supported', 'reason': 'Faithful'}
                        self.assertEqual(main([str(path), '--report', str(report), '--judge-runs', str(runs)]), 0)
                        self.assertEqual(judge.call_count, runs)
                        self.assertEqual(judge.call_args.args[0], command or DEFAULT_JUDGE)
                        self.assertIn(command or DEFAULT_JUDGE, report.read_text())

    def test_claude_adapter_with_fake_cli_no_live_calls(self):
        adapter = Path(__file__).resolve().parents[1] / 'tools/corpus_judge_claude.sh'
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / 'claude'
            args_path = Path(tmp) / 'args.json'
            input_path = Path(tmp) / 'input.json'
            cli.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                           "open(os.environ['ARGS_PATH'], 'w').write(json.dumps(sys.argv[1:]))\n"
                           "open(os.environ['INPUT_PATH'], 'w').write(sys.stdin.read())\n"
                           "print(os.environ['FAKE_CLAUDE_OUTPUT'])\nsys.exit(int(os.getenv('FAKE_EXIT', '0')))\n")
            cli.chmod(0o755)
            env = {**os.environ, 'PATH': tmp + os.pathsep + os.environ['PATH'],
                   'ARGS_PATH': str(args_path), 'INPUT_PATH': str(input_path)}
            payload = {'article_text': 'Молитва', 'source': 'Prayer'}
            for fenced in (False, True):
                verdict = json.dumps({'verdict': 'PASS', 'category': 'supported', 'reason': 'Supported'})
                if fenced:
                    verdict = '```json\n' + verdict + '\n```'
                env['FAKE_CLAUDE_OUTPUT'] = json.dumps({'result': verdict, 'is_error': False})
                result = subprocess.run([str(adapter)], input=json.dumps(payload), text=True, capture_output=True, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['verdict'], 'PASS')
                self.assertEqual(json.loads(input_path.read_text()), payload)
                self.assertEqual(json.loads(args_path.read_text()),
                                 ['-p', '--model', 'opus', '--output-format', 'json', '--tools', ''])
            for reply in ('{}', 'not json', '{"is_error":true,"result":"secret"}',
                          '{"result":"not json"}', '{"result":42}'):
                env['FAKE_CLAUDE_OUTPUT'] = reply
                result = subprocess.run([str(adapter)], input='{}', text=True, capture_output=True, env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('secret', result.stderr)
            env.update(FAKE_EXIT='1', FAKE_CLAUDE_OUTPUT=json.dumps({'result': '{"verdict":"PASS","category":"supported","reason":"ok"}'}))
            result = subprocess.run([str(adapter)], input='{}', text=True, capture_output=True, env=env)
            self.assertNotEqual(result.returncode, 0)

    def test_report_on_stale_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, report = Path(tmp) / 'ru.md', Path(tmp) / 'review.md'
            self.write_article(path, [self.item])
            self.api.hit['text_sha256'] = '0' * 64
            self.assertEqual(check_articles([path], self.api, self.judge, report), 1)
            self.assertIn('refresh evidence', report.read_text())


if __name__ == '__main__':
    unittest.main()
