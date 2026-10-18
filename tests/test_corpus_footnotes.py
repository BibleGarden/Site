"""Public footnote grouping; fragment evidence stays independent."""

import copy
from datetime import date
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as etree

import yaml
from markdown import Markdown
from markdown.extensions.footnotes import FootnoteExtension

from sitegen.content import parse_article, render_markdown
from sitegen.corpus import annotate, citations
from sitegen.corpus_footnotes import CorpusFootnotesProcessor, citation_key, occurrence_label
from test_corpus_citations import ITEM


class CorpusFootnotesTest(unittest.TestCase):
    def render(self, updates, order=None, lang='ru', ordinary=False):
        sources = [{**ITEM, 'id': f'source-{i}', **update} for i, update in enumerate(updates)]
        before = copy.deepcopy(sources)
        order = list(range(len(sources))) if order is None else order
        body = '\n\n'.join(sources[i]['text'] + f'[^corpus-source-{i}]' for i in order)
        if ordinary:
            body = 'Note[^ordinary].\n\n' + body + '\n\nAgain[^ordinary].\n\n[^ordinary]: An ordinary note.'
        self.assertEqual(citations(sources, body, 'fixture'), before)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f'{lang}.md'
            meta = dict(title='Fixture', description='Test', date=date(2026, 10, 18), corpus_sources=sources)
            path.write_text('---\n' + yaml.safe_dump(meta) + '---\n' + body, encoding='utf-8')
            rendered = parse_article(path, 'fixture', lang, {}, {}, {}, Path(tmp), site_key='lampada').body_html
        self.assertEqual(sources, before)
        return etree.fromstring('<article>' + rendered.replace('&#160;', ' ') + '</article>'), body, sources

    def assert_links_resolve(self, root):
        ids = [node.get('id') for node in root.iter() if node.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        for link in root.iter('a'):
            if link.get('href', '').startswith('#'):
                self.assertIn(link.get('href')[1:], ids)

    def test_groups_by_display_in_first_appearance_order_with_all_backlinks(self):
        root, _, _ = self.render([{}, {'chapter': 'Other'}, {}, {}], order=[2, 1, 0, 3])
        notes = root.findall('.//ol/li')
        self.assertEqual([note.get('id') for note in notes], ['fn:corpus-source-2', 'fn:corpus-source-1'])
        refs = root.findall('.//a[@class="footnote-ref"]')
        self.assertEqual([ref.text for ref in refs], ['1', '2', '1', '1'])
        self.assertEqual([ref.get('href') for ref in refs],
                         ['#fn:corpus-source-2', '#fn:corpus-source-1', '#fn:corpus-source-2', '#fn:corpus-source-2'])
        backs = notes[0].findall('.//a[@class="footnote-backref"]')
        self.assertEqual([back.text for back in backs], ['a', 'b', 'c'])
        self.assertEqual([back.get('href') for back in backs],
                         ['#fnref:corpus-source-2', '#fnref:corpus-source-0', '#fnref:corpus-source-3'])
        self.assertIn('↩', ''.join(notes[0].itertext()))
        self.assert_links_resolve(root)

    def test_distinct_public_metadata_stays_separate(self):
        for update in ({'author': 'Other'}, {'title': 'Other'}, {'chapter': 'Other'},
                       {'translator': 'Other'}, {'source_url': 'https://predanie.ru/other'},
                       {'translation': 'ours'}, {'chapter': None}, {'translator': None, 'translation': None}):
            with self.subTest(update=update):
                root, _, _ = self.render([{}, update])
                self.assertEqual(len(root.findall('.//ol/li')), 2)
                self.assert_links_resolve(root)

    def test_collapsible_whitespace_in_visible_citation_is_grouped(self):
        root, _, _ = self.render([{'chapter': 'Same  chapter'}, {'chapter': 'Same chapter'},
                                  {'chapter': 'Same\t\nchapter'}])
        self.assertEqual(len(root.findall('.//ol/li')), 1)
        self.assertEqual([ref.text for ref in root.findall('.//a[@class="footnote-ref"]')], ['1'] * 3)
        self.assert_links_resolve(root)
        self.assertEqual(citation_key('<a href="https://example.org/a?x=1&amp;y=2">Same\f chapter</a>'),
                         ('https://example.org/a?x=1&y=2', 'Same chapter'))

    def test_nonbreaking_spaces_and_url_whitespace_stay_distinct(self):
        root, _, _ = self.render([{'chapter': 'Same chapter'}, {'chapter': 'Same\u00a0chapter'}])
        self.assertEqual(len(root.findall('.//ol/li')), 2)
        self.assertNotEqual(citation_key('<a href="https://example.org/a  b">Same</a>'),
                            citation_key('<a href="https://example.org/a b">Same</a>'))

    def test_escaped_markup_in_label_is_visible_text(self):
        root, _, _ = self.render([{'chapter': '<Same> &  chapter'}, {'chapter': '<Same> & chapter'}])
        self.assertEqual(len(root.findall('.//ol/li')), 1)

    def test_private_evidence_differences_do_not_split_public_notes(self):
        root, _, _ = self.render([{}, {'kind': 'retelling', 'original': None, 'translation': None,
                                      'book_id': 6, 'chunk_id': 'other-chunk', 'char_start': 1, 'char_end': 5,
                                      'text_sha256': 'a' * 64, 'text': 'A different fragment.'}])
        self.assertEqual(len(root.findall('.//ol/li')), 1)

    def test_localized_accessible_backlinks_and_single_occurrence(self):
        for lang, label in [('en', 'Back to reference'), ('ru', 'Вернуться к сноске'),
                            ('uk', 'Повернутися до виноски')]:
            with self.subTest(lang=lang):
                root, _, _ = self.render([{}, {}, {'chapter': 'Other'}], lang=lang)
                backs = root.findall('.//a[@class="footnote-backref"]')
                self.assertEqual([''.join(back.itertext()) for back in backs], ['a', 'b', '↩'])
                self.assertEqual(len({back.get('aria-label') for back in backs}), 3)
                for back in backs:
                    self.assertTrue(back.get('aria-label').startswith(label))
                    self.assertEqual(back.get('aria-label'), back.get('title'))
                self.assertEqual(backs[-1].get('aria-label'), label + ' 2')
                self.assertIsNotNone(backs[-1].find('span[@aria-hidden="true"]'))
                paragraph = root.find('.//ol/li/p')
                arrow = paragraph.find('span[@aria-hidden="true"]')
                self.assertEqual(arrow.text, '↩')
                self.assertTrue(list(paragraph).index(arrow) < list(paragraph).index(backs[0]))

    def test_ordinary_notes_keep_distinct_content_and_repeated_backlinks(self):
        root, _, _ = self.render([{}, {}], ordinary=True)
        notes = root.findall('.//ol/li')
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0].get('id'), 'fn:ordinary')
        self.assertEqual(len(notes[0].findall('.//a[@class="footnote-backref"]')), 2)
        self.assertIn('An ordinary note.', ''.join(notes[0].itertext()))
        self.assert_links_resolve(root)

    def test_ordinary_footnotes_render_identically_without_corpus(self):
        body = 'First[^b], again[^b], second[^a].\n\n[^a]: Same.\n[^b]: Same.'
        self.assertEqual(render_markdown(body, lang="en"), render_markdown(body, corpus_sources=[], lang="en"))
        self.assertEqual(render_markdown(body, lang="en").count('<li id="fn:'), 2)

    def test_language_is_required(self):
        for sources in ([], [ITEM]):
            with self.subTest(sources=sources), self.assertRaisesRegex(TypeError, 'lang'):
                render_markdown('Text.', corpus_sources=sources)

    def test_ordinary_note_first_seen_after_corpus_is_renumbered(self):
        sources = [{**ITEM, 'id': 'first'}, {**ITEM, 'id': 'again'}]
        body = (ITEM['text'] + '[^corpus-first]\n\nOrdinary[^later].\n\n'
                + ITEM['text'] + '[^corpus-again]\n\nAgain[^later].\n\n'
                '[^later]: An ordinary note.')
        rendered = render_markdown(annotate(body, sources, 'en'), corpus_sources=sources, lang='en')
        root = etree.fromstring('<article>' + rendered + '</article>')
        self.assertEqual([ref.text for ref in root.findall('.//a[@class="footnote-ref"]')],
                         ['1', '2', '1', '2'])
        self.assertEqual([note.get('id') for note in root.findall('.//ol/li')],
                         ['fn:corpus-first', 'fn:later'])
        backs = root.findall('.//li[@id="fn:later"]//a[@class="footnote-backref"]')
        self.assertEqual(len(backs), 2)
        self.assertTrue(all(back.get('title') == 'Jump back to footnote 2 in the text' for back in backs))
        self.assert_links_resolve(root)

    def test_decorative_arrow_follows_citation_element(self):
        md = Markdown(extensions=['extra'])
        footnotes = next(ext for ext in md.registeredExtensions if isinstance(ext, FootnoteExtension))
        definition = '<a href="https://example.org">Source</a>'
        footnotes.footnotes.update({'corpus-first': definition, 'corpus-again': definition})
        root = etree.fromstring('''<article>
          <p><sup id="fnref:corpus-first"><a class="footnote-ref" href="#fn:corpus-first">1</a></sup>
          <sup id="fnref:corpus-again"><a class="footnote-ref" href="#fn:corpus-again">2</a></sup></p>
          <div class="footnote"><ol>
          <li id="fn:corpus-first"><p><a href="https://example.org">Source</a>
          <a class="footnote-backref" href="#fnref:corpus-first">↩</a></p></li>
          <li id="fn:corpus-again"><p><a href="https://example.org">Source</a>
          <a class="footnote-backref" href="#fnref:corpus-again">↩</a></p></li>
          </ol></div></article>''')
        CorpusFootnotesProcessor(md, footnotes, {'corpus-first', 'corpus-again'}, 'en').run(root)
        paragraph = root.find('.//ol/li/p')
        self.assertEqual([node.tag for node in paragraph], ['a', 'span', 'a', 'a'])
        self.assertEqual(paragraph[1].attrib, {'aria-hidden': 'true'})
        self.assertEqual(paragraph[1].text, '↩')
        self.assert_links_resolve(root)

    def test_backlink_labels_extend_past_z(self):
        self.assertEqual([occurrence_label(i) for i in [0, 25, 26, 27, 51, 52]],
                         ['a', 'z', 'aa', 'ab', 'az', 'ba'])
        root, _, _ = self.render([{} for _ in range(28)])
        backs = root.findall('.//a[@class="footnote-backref"]')
        self.assertEqual([back.text for back in backs][-3:], ['z', 'aa', 'ab'])
        self.assert_links_resolve(root)

    def test_ordinary_note_with_same_citation_is_not_grouped(self):
        _, body, sources = self.render([{}, {}])
        citation = annotate('', sources[:1], 'ru').split(': ', 1)[1].strip()
        rendered = render_markdown(annotate('Note[^ordinary].\n\n' + body + '\n\n[^ordinary]: ' + citation,
                                            sources, 'ru'), corpus_sources=sources, lang='ru')
        self.assertEqual(rendered.count('<li id="fn:'), 2)
