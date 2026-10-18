import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from tools import corpus_research as research


def hit(book_id=1, section=1, score=0.5, chunk='one'):
    return {
        'book': {'id': book_id, 'author': 'Author', 'title': 'Book',
                 'tradition': 'Tradition', 'language': 'ru', 'translator': None,
                 'source_url': 'https://example.org/book', 'license': 'public_domain'},
        'chunk_id': chunk, 'section_index': section, 'chapter': 'Structural wrapper', 'citation_label': 'Chapter',
        'section_path': 'Chapter / Section', 'char_start': 10, 'char_end': 300,
        'text_sha256': 'a' * 64, 'text': 'Молитва — живой разговор. ' * 30,
        'score': score,
    }


class FakeAPI:
    def __init__(self, batches):
        self.batches = iter(batches)
        self.requests = []

    def request(self, path, data=None):
        self.requests.append((path, copy.deepcopy(data)))
        if path == '/books':
            return {'books': [dict(hit()['book'], status='indexed'),
                              dict(hit(2)['book'], status='missing_sources')]}
        batch = next(self.batches)
        if isinstance(batch, Exception):
            raise batch
        return {'results': batch}


class ResearchTests(unittest.TestCase):
    def test_labels_are_required_and_never_replaced_by_chapter(self):
        for label in (None, 1, '  '):
            candidate = hit()
            candidate['citation_label'] = label
            with self.assertRaisesRegex(research.ResearchError, 'citation_label'):
                research.collect(FakeAPI([[candidate]]), [{'query': 'prayer'}])
        candidate = hit()
        del candidate['citation_label']
        with self.assertRaisesRegex(research.ResearchError, 'citation_label'):
            research.collect(FakeAPI([[candidate]]), [{'query': 'prayer'}])
        for label in ('II — 3. Prayer', ''):
            candidate = hit()
            candidate['citation_label'] = label
            inventory, selected, counts = research.collect(FakeAPI([[candidate]]), [{'query': 'prayer'}])
            output = research.render('Topic', [{'query': 'prayer'}], inventory, selected, counts)
            self.assertIn(label or 'нет подтверждённой метки', output)
            self.assertNotIn('Structural wrapper', output)

    def test_best_per_book_section_and_query_provenance(self):
        api = FakeAPI([[hit(score=.4), hit(2, score=.6)],
                       [hit(score=.9, chunk='better'), hit(section=2, score=.7)],
                       [hit(score=.3)]])
        queries = [{'query': 'ru', 'language': 'ru'},
                   {'query': 'en', 'author': 'Author'}, {'query': 'fr'}]
        _, selected, counts = research.collect(api, queries)
        self.assertEqual(counts, [2, 2, 1])
        self.assertEqual([x['hit']['chunk_id'] for x in selected], ['better', 'one', 'one'])
        self.assertEqual(selected[0]['queries'], {1, 2, 3})
        self.assertEqual(len({(x['hit']['book']['id'], x['hit']['section_index']) for x in selected}), 3)
        self.assertEqual(api.requests[1:], [('/search', q) for q in queries])

    def test_limits_leave_room_for_other_books(self):
        api = FakeAPI([[hit(section=1, score=.9), hit(section=2, score=.8),
                        hit(section=3, score=.7), hit(2, score=.6), hit(3, score=.5)]])
        _, selected, _ = research.collect(api, [{'query': 'q'}], max_per_book=1, max_hits=2)
        self.assertEqual([x['hit']['book']['id'] for x in selected], [1, 2])

    def test_explicit_delay_between_queries_without_retry(self):
        api = FakeAPI([[hit()], [hit(2)], [hit(3)]])
        with patch.object(research.time, 'sleep') as sleep:
            research.collect(api, [{'query': 'a'}, {'query': 'b'}, {'query': 'c'}], query_delay=5)
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(5), unittest.mock.call(5)])
        self.assertEqual(len(api.requests), 4)

    def test_empty_query_is_visible_but_all_empty_fails(self):
        _, selected, counts = research.collect(FakeAPI([[], [hit()]]), [{'query': 'a'}, {'query': 'b'}])
        self.assertEqual(counts, [0, 1])
        self.assertEqual(len(selected), 1)
        with self.assertRaisesRegex(research.ResearchError, 'No hits'):
            research.collect(FakeAPI([[]]), [{'query': 'none'}])

    def test_dossier_has_bounded_unicode_excerpt_and_evidence(self):
        inventory, selected, counts = research.collect(FakeAPI([[hit()]]), [{'query': 'молитва'}])
        dossier = research.render('Topic', [{'query': 'молитва'}], inventory, selected, counts, 10)
        for expected in ['Author', 'Tradition', 'ru', 'Chapter', 'Section',
                         '`one`', 'score: 0.5', '[10, 300)', 'a' * 64,
                         r'missing\_sources', 'GET /books', 'Мария ещё не утвердила',
                         '> Молитва —\n', 'scope=chapter']:
            self.assertIn(expected, dossier)
        self.assertNotIn(hit()['text'], dossier)
        self.assertNotIn('> Молитва — ж', dossier)

    def test_excerpt_selects_matching_sentence_not_chunk_prefix(self):
        text = 'Unrelated introduction. I speak to God — simply! Another sentence.'
        self.assertEqual(research.excerpt_around_match(text, ['God simply'], 180),
                         'I speak to God — simply!')
        self.assertIsNone(research.excerpt_around_match(text, ['тишина'], 180))
        self.assertEqual(research.excerpt_around_match(
            'You are here. Prayer can be honest.', ['how did you learn prayer'], 180),
            'Prayer can be honest.')

    def test_long_sentence_window_keeps_late_match_and_punctuation(self):
        text = 'Unrelated words ' * 40 + 'prayer — honest words!'
        excerpt = research.excerpt_around_match(text, ['prayer honest'], 70)
        self.assertIn('prayer — honest words!', excerpt)
        self.assertLessEqual(len(excerpt), 70)
        self.assertIn(excerpt, text)

    def test_existing_dossier_requires_force_before_api_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'd.md'
            output.write_text('editorial notes')
            queries = Path(directory) / 'q.json'
            queries.write_text('[{"query":"prayer"}]')
            with patch.object(research, 'CorpusAPI') as api, contextlib.redirect_stderr(io.StringIO()):
                result = research.main(['--queries', str(queries), '--topic', 'Topic', '--output', str(output)])
            self.assertEqual(result, 1)
            self.assertEqual(output.read_text(), 'editorial notes')
            api.assert_not_called()

    def test_force_explicitly_replaces_existing_dossier(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'd.md'
            queries = Path(directory) / 'q.json'
            output.write_text('old dossier')
            queries.write_text('[{"query":"молитва"}]')
            with patch.object(research, 'CorpusAPI', return_value=FakeAPI([[hit()]])), contextlib.redirect_stdout(io.StringIO()):
                result = research.main(['--queries', str(queries), '--topic', 'Topic', '--output', str(output), '--force'])
            self.assertEqual(result, 0)
            self.assertNotIn('old dossier', output.read_text())
            self.assertIn('Досье: Topic', output.read_text())

    def test_untrusted_metadata_cannot_inject_markdown_or_html(self):
        self.assertEqual(research.md('<script>\n# title [x](y)'), r'\<script\> \# title \[x\](y)')
        self.assertEqual(research.md(None), 'не указано в API')

    def test_invalid_query_files_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'q.json'
            for value in [[], {}, ['q'], [{'query': ' '}], [{'query': 'q', 'unknown': 1}]]:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value))
                    with self.assertRaises(research.ResearchError):
                        research.load_queries(path)

    def test_cli_failure_never_writes_partial_dossier_or_retries(self):
        api = FakeAPI([[hit()], research.ResearchError('Corpus HTTP 503')])
        with tempfile.TemporaryDirectory() as directory:
            queries = Path(directory) / 'q.json'
            output = Path(directory) / 'd.md'
            queries.write_text('[{"query":"one"},{"query":"two"}]')
            output.write_text('previous dossier')
            with patch.object(research, 'CorpusAPI', return_value=api), contextlib.redirect_stderr(io.StringIO()):
                result = research.main(['--queries', str(queries), '--topic', 'Topic', '--output', str(output), '--force'])
            self.assertEqual(result, 1)
            self.assertEqual(output.read_text(), 'previous dossier')
            self.assertEqual(len(api.requests), 3)

    def test_cli_success_with_fake_api(self):
        with tempfile.TemporaryDirectory() as directory:
            queries = Path(directory) / 'q.json'
            output = Path(directory) / 'd.md'
            queries.write_text('[{"query":"one","tradition":"Tradition"}]')
            with patch.object(research, 'CorpusAPI', return_value=FakeAPI([[hit()]])), contextlib.redirect_stdout(io.StringIO()):
                result = research.main(['--queries', str(queries), '--topic', 'Topic', '--output', str(output)])
            self.assertEqual(result, 0)
            self.assertIn('# Досье: Topic', output.read_text())

    def test_missing_key_fails_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(research, 'urlopen') as request:
            with self.assertRaisesRegex(research.ResearchError, 'CORPUS_API_KEY'):
                research.CorpusAPI('http://localhost', '')
            request.assert_not_called()

    def test_transport_posts_exact_filters_and_private_auth(self):
        response = io.BytesIO(b'{"results": []}')
        api = research.CorpusAPI('http://example.test/', 'private-key')
        payload = {'query': 'prayer', 'language': 'en', 'limit': 4}
        with patch.object(research, 'urlopen', return_value=response) as request:
            self.assertEqual(api.request('/search', payload), {'results': []})
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, 'http://example.test/api/v1/channels/lampada/search')
        self.assertEqual(sent.get_method(), 'POST')
        self.assertEqual(sent.get_header('X-api-key'), 'private-key')
        self.assertEqual(json.loads(sent.data), payload)

    def test_transport_errors_are_explicit_without_body_or_retry(self):
        api = research.CorpusAPI('http://example.test', 'private-key')
        for error in [HTTPError('url', 409, 'private detail', {}, None), TimeoutError()]:
            with self.subTest(error=error), patch.object(research, 'urlopen', side_effect=error) as request:
                with self.assertRaises(research.ResearchError) as caught:
                    api.request('/books')
                self.assertNotIn('private', str(caught.exception))
                self.assertEqual(request.call_count, 1)
        with patch.object(research, 'urlopen', return_value=io.BytesIO(b'not json')):
            with self.assertRaisesRegex(research.ResearchError, 'invalid JSON'):
                api.request('/books')


if __name__ == '__main__':
    unittest.main()
