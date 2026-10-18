"""Exact migration and stale-report protection without network or LLM calls."""

import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sitegen.content import FRONTMATTER_RE
from tools import reanchor_corpus_sources as reanchor
from tools.check_corpus_citations import CheckError
from test_corpus_citations import BOOK, ITEM, TEXT, START, END
import test_corpus_citations as fixtures


class FakeAPI:
    base_url = 'http://fake/api/v1/channels/lampada'

    def __init__(self, text=TEXT, bounds=None, label='Part I — 2. Prayer'):
        self.book = dict(book=copy.deepcopy(BOOK), text=text,
                         text_sha256=reanchor.sha(text.encode()), sections=[])
        bounds = bounds if bounds is not None else [(0, len(text))]
        self.chunks = [dict(chunk_id=f'book-5-{i:04d}', book=copy.deepcopy(BOOK),
                            text=text[start:end], char_start=start, char_end=end,
                            text_sha256=self.book['text_sha256'], chapter='Structural wrapper',
                            citation_label=label) for i, (start, end) in enumerate(bounds)]
        self.calls = []

    def request(self, path, data=None):
        self.calls.append((path, data))
        if path == '/books':
            return {'books': [dict(id=5, status='indexed', chunks_count=len(self.chunks))]}
        if path == '/books/5/text':
            return copy.deepcopy(self.book)
        if path == '/search/chunks':
            return {'chunks': [copy.deepcopy(chunk) for chunk in self.chunks if chunk['chunk_id'] in data['ids']]}
        if path == '/search/context':
            start, end = data['char_start'], data['char_end']
            chunk = next(chunk for chunk in self.chunks if chunk['char_start'] <= start < end <= chunk['char_end'])
            return dict(book=copy.deepcopy(BOOK), text=self.book['text'][start:end],
                        text_sha256=self.book['text_sha256'], char_start=start, char_end=end,
                        citation_label=chunk['citation_label'])
        raise AssertionError(path)


class ReanchorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.backup = self.root / 'backup'
        self.base = self.backup / 'data/lampada/texts/book_5'
        self.base.parent.mkdir(parents=True)
        self.base.with_suffix('.txt').write_bytes(TEXT.encode())
        self.base.with_suffix('.json').write_text(json.dumps({'text_sha256': ITEM['text_sha256']}))
        self.path = self.root / 'ru.md'
        self.item = copy.deepcopy(ITEM)
        fixture = fixtures.CitationTest()
        fixture.item = self.item
        fixture.write_article(self.path, [self.item])
        self.api = FakeAPI()

    def report(self, paths=None, api=None):
        return dict(schema=1, snapshots=str(self.backup), api_url=self.api.base_url,
                    articles=reanchor.plan(paths or [self.path], self.backup, api or self.api))

    def entry(self, api=None):
        return self.report(api=api)['articles'][0]['sources'][0]

    def test_same_text_keeps_offsets_and_replaces_only_anchor_scalars(self):
        original = self.path.read_bytes()
        report = self.report()
        self.assertEqual(self.path.read_bytes(), original)
        source = report['articles'][0]['sources'][0]
        self.assertEqual(source['status'], 'ready')
        self.assertTrue(source['text_unchanged'])
        self.assertEqual((source['after']['char_start'], source['after']['char_end']), (START, END))
        reanchor.apply_report(report, self.api)
        result = self.path.read_text()
        self.assertEqual(result, original.decode().replace('book-5-1', '"book-5-0000"')
                         .replace('chapter: Prayer', 'chapter: "Part I — 2. Prayer"'))
        self.assertEqual(FRONTMATTER_RE.match(result)[2], FRONTMATTER_RE.match(original.decode())[2])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)

    def test_changed_text_moves_exact_unique_unicode_fragment(self):
        api = FakeAPI('Новая вводная 🌿\n' + TEXT)
        source = self.entry(api)
        self.assertEqual(source['status'], 'ready')
        self.assertFalse(source['text_unchanged'])
        self.assertEqual(source['after']['char_start'], START + len('Новая вводная 🌿\n'))
        self.assertEqual(source['after']['text_sha256'], api.book['text_sha256'])

    def test_unchanged_duplicate_fragment_retains_original_offsets(self):
        text = TEXT + TEXT[START:END]
        self.base.with_suffix('.txt').write_bytes(text.encode())
        digest = reanchor.sha(text.encode())
        self.base.with_suffix('.json').write_text(json.dumps({'text_sha256': digest}))
        for start in (START, len(TEXT)):
            self.item.update(text_sha256=digest, char_start=start, char_end=start + END - START)
            fixture = fixtures.CitationTest()
            fixture.item = self.item
            fixture.write_article(self.path, [self.item])
            source = self.entry(FakeAPI(text))
            self.assertEqual(source['status'], 'ready')
            self.assertEqual(source['after']['char_start'], start)

    def test_changed_text_with_duplicate_old_fragment_requires_manual_review(self):
        fragment = TEXT[START:END]
        old = TEXT + '\n' + fragment
        self.base.with_suffix('.txt').write_bytes(old.encode())
        digest = reanchor.sha(old.encode())
        self.base.with_suffix('.json').write_text(json.dumps({'text_sha256': digest}))
        for start in (START, len(TEXT) + 1):
            self.item.update(text_sha256=digest, char_start=start, char_end=start + len(fragment))
            fixture = fixtures.CitationTest()
            fixture.item = self.item
            fixture.write_article(self.path, [self.item])
            source = self.entry(FakeAPI(TEXT))
            self.assertEqual(source['status'], 'manual')
            self.assertIn('ambiguous matches in the old text', source['reason'])

    def test_removed_ambiguous_and_overlapping_matches_require_manual_review(self):
        for text, reason in ((TEXT.replace(TEXT[START:END], 'Edited'), 'removed'),
                             ('Prefix ' + TEXT + TEXT[START:END], 'ambiguous')):
            source = self.entry(FakeAPI(text))
            self.assertEqual(source['status'], 'manual')
            self.assertIn(reason, source['reason'])
        # The second overlapping occurrence must count as ambiguous too.
        self.item.update(kind='retelling', text='Pray with love and care.', original=None, translation=None,
                         char_start=0, char_end=3)
        self.base.with_suffix('.txt').write_bytes(b'aaa')
        digest = reanchor.sha(b'aaa')
        self.base.with_suffix('.json').write_text(json.dumps({'text_sha256': digest}))
        self.item['text_sha256'] = digest
        fixture = fixtures.CitationTest()
        fixture.item = self.item
        fixture.write_article(self.path, [self.item])
        source = self.entry(FakeAPI('aaaa'))
        self.assertEqual(source['status'], 'manual')
        self.assertIn('ambiguous', source['reason'])

    def test_boundary_missing_and_duplicate_chunks_require_manual_review(self):
        for bounds in ([(0, START + 5), (START + 5, len(TEXT))],
                       [(0, START)], [(0, len(TEXT)), (0, len(TEXT))]):
            source = self.entry(FakeAPI(bounds=bounds))
            self.assertEqual(source['status'], 'manual')
            self.assertIn('chunk', source['reason'])

    def test_corrupt_old_snapshot_hash_and_range_abort_report(self):
        api = FakeAPI('Prefix ' + TEXT)
        for field, value in (('text_sha256', 'f' * 64), ('char_end', len(TEXT) + 10)):
            text = self.path.read_text()
            self.path.write_text(text.replace(f"{field}: {self.item[field]}", f"{field}: {value}"))
            with self.assertRaisesRegex(CheckError, 'hash/range'):
                self.entry(api)
            self.path.write_text(text)
        self.base.with_suffix('.txt').write_bytes(b'corrupt')
        with self.assertRaisesRegex(CheckError, 'Old sidecar hash'):
            self.entry(api)

    def test_original_absent_from_old_fragment_requires_manual_review(self):
        self.path.write_text(self.path.read_text().replace(
            f"original: {self.item['original']}", 'original: Not in the source'))
        source = self.entry()
        self.assertEqual(source['status'], 'manual')
        self.assertIn('Original quotation', source['reason'])

    def test_unchanged_hash_needs_no_snapshot(self):
        self.base.with_suffix('.json').unlink()
        self.base.with_suffix('.txt').unlink()
        with patch.object(reanchor.Migration, 'old_text', side_effect=AssertionError('Must not read snapshots')):
            report = self.report()
            self.assertTrue(report['articles'][0]['sources'][0]['text_unchanged'])
            reanchor.apply_report(report, self.api)
        self.assertIn('Part I', self.path.read_text())

    def test_changed_hash_requires_snapshot(self):
        self.base.with_suffix('.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.entry(FakeAPI('Changed ' + TEXT))

    def test_current_book_chunk_metadata_and_context_corruption_fail_closed(self):
        for target, key, value in (('book', 'text', 'corrupt'),
                                    ('chunk', 'text_sha256', '0' * 64),
                                    ('chunk', 'text', 'corrupt'),
                                    ('chunk', 'citation_label', None)):
            api = FakeAPI()
            (api.book if target == 'book' else api.chunks[0])[key] = value
            with self.assertRaises((CheckError, ValueError)):
                self.entry(api)
        api = FakeAPI()
        api.book['book']['author'] = 'Different author'
        api.chunks[0]['book']['author'] = 'Different author'
        self.assertIn('metadata changed', self.entry(api)['reason'])
        api = FakeAPI()
        request = api.request
        def corrupt_context(path, data=None):
            response = request(path, data)
            if path == '/search/context':
                response['citation_label'] = 'Wrong'
            return response
        api.request = corrupt_context
        with self.assertRaisesRegex(CheckError, 'context'):
            self.entry(api)

    def test_null_locator_and_metadata_only_retelling_migration(self):
        self.item.update(kind='retelling', original=None, translation=None)
        fixture = fixtures.CitationTest()
        fixture.item = self.item
        fixture.write_article(self.path, [self.item])
        api = FakeAPI(label='')
        report = self.report(api=api)
        self.assertIsNone(report['articles'][0]['sources'][0]['after']['chapter'])
        reanchor.apply_report(report, api)
        self.assertIn('chapter: null', self.path.read_text())

    def test_no_article_is_written_if_any_article_changed_since_report(self):
        other = self.root / 'en.md'
        other.write_bytes(self.path.read_bytes())
        report = self.report([self.path, other])
        original = self.path.read_bytes()
        other.write_bytes(other.read_bytes() + b'\nChanged')
        with self.assertRaisesRegex(CheckError, 'Article changed since report'):
            reanchor.apply_report(report, self.api)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob('.reanchor-*')), [])

    def test_corpus_snapshot_and_report_mutations_block_apply(self):
        report = self.report()
        original = self.path.read_bytes()
        changed = FakeAPI(label='A new locator')
        with self.assertRaisesRegex(CheckError, 'changed since report'):
            reanchor.apply_report(report, changed)
        report['articles'][0]['sources'][0]['after']['char_start'] = 0
        with self.assertRaisesRegex(CheckError, 'changed since report'):
            reanchor.apply_report(report, self.api)
        api = FakeAPI('Prefix ' + TEXT)
        report = self.report(api=api)
        self.base.with_suffix('.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(CheckError, 'Old sidecar hash'):
            reanchor.apply_report(report, api)
        self.assertEqual(self.path.read_bytes(), original)

    def test_manual_cases_prevent_any_apply(self):
        report = self.report(api=FakeAPI('Edited'))
        original = self.path.read_bytes()
        with self.assertRaisesRegex(CheckError, 'manual cases'):
            reanchor.apply_report(report, self.api)
        self.assertEqual(self.path.read_bytes(), original)

    def test_folded_locator_and_comments_preserve_body_and_other_metadata(self):
        self.path.write_text(self.path.read_text().replace('chapter: Prayer', 'chapter: >-\n    Prayer')
                             .replace('title: Fixture', 'title: Fixture # editorial comment'))
        original = self.path.read_text()
        reanchor.apply_report(self.report(), self.api)
        updated = self.path.read_text()
        self.assertEqual(FRONTMATTER_RE.match(original)[2], FRONTMATTER_RE.match(updated)[2])
        self.assertIn('title: Fixture # editorial comment', updated)
        self.assertIn('chapter: "Part I — 2. Prayer"\n', updated)

    def test_crlf_articles_preserve_all_bytes_except_anchor_values(self):
        for folded in (False, True):
            fixture = fixtures.CitationTest()
            fixture.item = self.item
            fixture.write_article(self.path, [self.item])
            text = self.path.read_text()
            if folded:
                text = text.replace('chapter: Prayer', 'chapter: >-\n    Prayer')
            original = text.replace('\n', '\r\n').encode()
            self.path.write_bytes(original)
            report = self.report()
            reanchor.apply_report(report, self.api)
            expected = original.replace(b'book-5-1', b'"book-5-0000"')
            old = b'chapter: >-\r\n    Prayer\r\n' if folded else b'chapter: Prayer\r\n'
            expected = expected.replace(old, 'chapter: "Part I — 2. Prayer"\r\n'.encode())
            self.assertEqual(self.path.read_bytes(), expected)

    def test_semantic_preflight_rejects_unplanned_evidence_changes(self):
        report = self.report()
        original = self.path.read_bytes()
        patch_anchors = reanchor.patch_anchors
        for before, after in ((b'author: Author', b'author: Wrong'),
                               (b'char_start: 18', b'char_start: 19')):
            def corrupt_patch(raw, entries):
                return patch_anchors(raw, entries).replace(before, after)
            with patch.object(reanchor, 'patch_anchors', side_effect=corrupt_patch), \
                 self.assertRaisesRegex(CheckError, 'Staged evidence differs'):
                reanchor.apply_report(report, self.api)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(list(self.root.glob('.reanchor-*')), [])

    def test_missing_report_source_has_explicit_diagnostic(self):
        entry = self.entry()
        entry['id'] = 'different'
        with self.assertRaisesRegex(CheckError, "Article source ID 'prayer' is missing from the report"):
            reanchor.patch_anchors(self.path.read_bytes(), [entry])

    def test_programming_errors_propagate_from_plan(self):
        for error in (KeyError('unexpected'), TypeError('unexpected')):
            with patch.object(reanchor.Migration, 'source', side_effect=error), \
                 self.assertRaises(type(error)):
                self.report()

    def test_infrastructure_error_during_apply_preserves_its_diagnostic(self):
        report = self.report()
        original = self.path.read_bytes()
        with patch.object(self.api, 'request', side_effect=CheckError('Corpus HTTP 503')), \
             self.assertRaisesRegex(CheckError, 'Corpus HTTP 503'):
            reanchor.apply_report(report, self.api)
        self.assertEqual(self.path.read_bytes(), original)

    def test_cli_infrastructure_errors_abort_without_report_or_article_writes(self):
        report = self.root / 'report.json'
        original = self.path.read_bytes()
        for error in (CheckError('Corpus HTTP 409'), CheckError('Corpus HTTP 503'), OSError('Network disconnected')):
            with patch.object(reanchor, 'CorpusAPI', return_value=self.api), \
                 patch.object(self.api, 'request', side_effect=error) as request, \
                 patch('sys.stderr', new_callable=io.StringIO) as stderr:
                self.assertEqual(reanchor.main([str(self.path), '--snapshots', str(self.backup),
                                                '--report', str(report)]), 1)
                self.assertIn(str(error), stderr.getvalue())
                self.assertEqual(request.call_count, 1)
            self.assertFalse(report.exists())
            self.assertEqual(self.path.read_bytes(), original)

    def test_anchor_alias_cannot_rewrite_another_metadata_field(self):
        text = self.path.read_text().replace('author: Author', 'author: &author Author')
        self.path.write_text(text.replace('chapter: Prayer', 'chapter: *author'))
        original = self.path.read_bytes()
        with self.assertRaisesRegex(CheckError, 'explicit scalars'):
            reanchor.apply_report(self.report(), self.api)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.glob('.reanchor-*')), [])

    def test_article_edit_during_api_revalidation_is_detected(self):
        report = self.report()
        api = FakeAPI()
        request = api.request
        def edit_article(path, data=None):
            if path == '/search/context':
                self.path.write_bytes(self.path.read_bytes() + b'\nConcurrent edit')
            return request(path, data)
        api.request = edit_article
        with self.assertRaisesRegex(CheckError, 'during revalidation'):
            reanchor.apply_report(report, api)
        self.assertNotIn('Part I', self.path.read_text())

    def test_incomplete_inventory_and_http_failures_abort_without_retry(self):
        for failure in (CheckError('Corpus HTTP 409'), CheckError('Corpus HTTP 503'), None):
            api = FakeAPI()
            request = api.request
            calls = []
            def incomplete(path, data=None):
                if path == '/search/chunks':
                    calls.append(path)
                    if failure:
                        raise failure
                    return {'chunks': []}
                return request(path, data)
            api.request = incomplete
            other = self.root / 'en.md'
            other.write_bytes(self.path.read_bytes())
            with self.assertRaises(CheckError):
                self.report([self.path, other], api)
            self.assertEqual(len(calls), 1)

    def test_reports_deduplicate_book_reads_and_fetch_chunks_in_batches(self):
        text = TEXT + 'x' * 101
        api = FakeAPI(text, [(0, len(TEXT))] + [(len(TEXT) + i, len(TEXT) + i + 1) for i in range(101)])
        other = self.root / 'en.md'
        other.write_bytes(self.path.read_bytes())
        report = self.report([self.path, other], api)
        self.assertTrue(all(a['sources'][0]['status'] == 'ready' for a in report['articles']))
        self.assertEqual(sum(path == '/books/5/text' for path, _ in api.calls), 1)
        self.assertEqual([len(data['ids']) for path, data in api.calls if path == '/search/chunks'], [100, 2])

    def test_cli_report_and_explicit_apply(self):
        report = self.root / 'report.json'
        original = self.path.read_bytes()
        with patch.dict(os.environ, {'CORPUS_API_KEY': 'private'}), \
             patch.object(reanchor, 'CorpusAPI', return_value=self.api), patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(reanchor.main([str(self.path), '--snapshots', str(self.backup), '--report', str(report)]), 0)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(reanchor.main(['--apply', str(report)]), 0)
        self.assertNotEqual(self.path.read_bytes(), original)

    def test_cli_refuses_report_overwrite_and_wrong_api(self):
        report = self.root / 'report.json'
        report.write_text(json.dumps(self.report()))
        with patch.object(reanchor, 'CorpusAPI', return_value=self.api), \
             patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(reanchor.main([str(self.path), '--snapshots', str(self.backup), '--report', str(report)]), 1)
            self.api.base_url = 'http://different/api/v1/channels/lampada'
            self.assertEqual(reanchor.main(['--apply', str(report)]), 1)


if __name__ == '__main__':
    unittest.main()
