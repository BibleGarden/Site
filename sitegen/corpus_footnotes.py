"""Group public corpus footnotes while preserving every evidence marker."""

import re
from html.parser import HTMLParser
from collections.abc import Mapping, Sequence
from typing import Any
from xml.etree import ElementTree as etree

from markdown import Markdown
from markdown.extensions import Extension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.treeprocessors import Treeprocessor


BACK_LABELS = {
    'en': ('Back to reference {number}', 'Back to reference {number}, occurrence {occurrence}'),
    'ru': ('Вернуться к сноске {number}', 'Вернуться к сноске {number}, упоминание {occurrence}'),
    'uk': ('Повернутися до виноски {number}', 'Повернутися до виноски {number}, згадка {occurrence}'),
}


class CitationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.url: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'a':
            self.url = dict(attrs)['href']

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def citation_key(definition: str) -> tuple[str, str]:
    """Match visible text using HTML collapsible whitespace, keeping the URL exact."""
    parser = CitationParser()
    parser.feed(definition)
    parser.close()
    assert parser.url is not None
    label = re.sub(r'[ \t\n\r\f]+', ' ', ''.join(parser.text)).strip(' ')
    return parser.url, label


def occurrence_label(index: int) -> str:
    """Return a, ..., z, aa, ... for an occurrence (zero based)."""
    label = ""
    while index >= 0:
        index, digit = divmod(index, 26)
        label = chr(97 + digit) + label
        index -= 1
    return label


class CorpusFootnotesExtension(Extension):
    def __init__(self, sources: Sequence[Mapping[str, Any]], lang: str) -> None:
        self.ids = {f'corpus-{item["id"]}' for item in sources}
        self.lang = lang
        super().__init__()

    def extendMarkdown(self, md: Markdown) -> None:
        footnotes = next(ext for ext in md.registeredExtensions if isinstance(ext, FootnoteExtension))
        # Run after Markdown has created references and duplicate ordinary backlinks.
        md.treeprocessors.register(
            CorpusFootnotesProcessor(md, footnotes, self.ids, self.lang), 'corpus-footnotes', 14,
        )


class CorpusFootnotesProcessor(Treeprocessor):
    def __init__(self, md: Markdown, footnotes: FootnoteExtension, ids: set[str], lang: str) -> None:
        super().__init__(md)
        self.footnotes = footnotes
        self.ids = ids
        self.lang = lang

    def run(self, root: etree.Element) -> None:
        notes = root.find('.//div[@class="footnote"]/ol')
        if notes is None:
            return
        items = {item.attrib['id']: item for item in notes}
        # Corpus definitions contain only the escaped public label and source link.
        definitions = {
            self.footnotes.makeFootnoteId(ident): citation_key(self.footnotes.footnotes[ident])
            for ident in self.ids
        }
        groups: dict[tuple[str, str], str] = {}
        ordered: dict[str, etree.Element] = {}
        occurrences: dict[str, list[tuple[etree.Element, str]]] = {}
        for sup in root.iter('sup'):
            ref = sup.find('a[@class="footnote-ref"]')
            if ref is None:
                continue
            ident = ref.attrib['href'][1:]
            if ident in definitions:
                ident = groups.setdefault(definitions[ident], ident)
            ordered.setdefault(ident, items[ident])
            refs = occurrences.setdefault(ident, [])
            refs.append((ref, sup.attrib['id']))
            ref.set('href', '#' + ident)

        # Unreferenced ordinary definitions retain their original order.
        for ident, item in items.items():
            if ident not in definitions:
                ordered.setdefault(ident, item)
        notes[:] = list(ordered.values())
        for number, (ident, item) in enumerate(ordered.items(), 1):
            refs = occurrences.get(ident, [])
            for ref, _ in refs:
                ref.text = str(number)
            if ident not in definitions:
                for back in item.iter('a'):
                    if back.get('class') == 'footnote-backref':
                        back.set('title', self.footnotes.getConfig('BACKLINK_TITLE').format(number))
                continue
            paragraph = item.find('p')
            assert paragraph is not None
            for back in list(paragraph):
                if back.get('class') == 'footnote-backref':
                    paragraph.remove(back)
            if len(refs) > 1:
                arrow = etree.SubElement(paragraph, 'span', {'aria-hidden': 'true'})
                arrow.text, arrow.tail = '↩', ' '
            for index, (_, ref_id) in enumerate(refs):
                template = BACK_LABELS[self.lang][1 if len(refs) > 1 else 0]
                label = template.format(number=number, occurrence=index + 1)
                back = etree.SubElement(paragraph, 'a', {
                    'class': 'footnote-backref', 'href': '#' + ref_id,
                    'aria-label': label, 'title': label,
                })
                if len(refs) > 1:
                    back.text = occurrence_label(index)
                else:
                    etree.SubElement(back, 'span', {'aria-hidden': 'true'}).text = '↩'
                back.tail = ' ' if index + 1 < len(refs) else ''
