"""Group public corpus footnotes while preserving every evidence marker."""

from xml.etree import ElementTree as etree

from markdown.extensions import Extension
from markdown.extensions.footnotes import FootnoteExtension
from markdown.treeprocessors import Treeprocessor


def occurrence_label(index):
    """Return a, ..., z, aa, ... for an occurrence (zero based)."""
    label = ""
    while index >= 0:
        index, digit = divmod(index, 26)
        label = chr(97 + digit) + label
        index -= 1
    return label


class CorpusFootnotesExtension(Extension):
    def __init__(self, sources, lang):
        self.ids = {f'corpus-{item["id"]}' for item in sources}
        self.lang = lang
        super().__init__()

    def extendMarkdown(self, md):
        footnotes = next(ext for ext in md.registeredExtensions if isinstance(ext, FootnoteExtension))
        # Run after Markdown has created references and duplicate ordinary backlinks.
        md.treeprocessors.register(
            CorpusFootnotesProcessor(md, footnotes, self.ids, self.lang), 'corpus-footnotes', 14,
        )


class CorpusFootnotesProcessor(Treeprocessor):
    def __init__(self, md, footnotes, ids, lang):
        super().__init__(md)
        self.footnotes = footnotes
        self.ids = ids
        self.lang = lang

    def run(self, root):
        notes = root.find('.//div[@class="footnote"]/ol')
        if notes is None:
            return
        items = {item.get('id'): item for item in notes}
        # Corpus definitions contain only the escaped public label and source link.
        definitions = {
            self.footnotes.makeFootnoteId(ident): self.footnotes.footnotes[ident]
            for ident in self.ids
        }
        groups, ordered, occurrences = {}, {}, {}
        for sup in root.iter('sup'):
            ref = sup.find('a[@class="footnote-ref"]')
            if ref is None:
                continue
            ident = ref.get('href')[1:]
            if ident in definitions:
                ident = groups.setdefault(definitions[ident], ident)
            ordered.setdefault(ident, items[ident])
            refs = occurrences.setdefault(ident, [])
            refs.append((ref, sup.get('id')))
            ref.set('href', '#' + ident)

        # Unreferenced ordinary definitions retain their original order.
        for ident, item in items.items():
            if ident not in definitions:
                ordered.setdefault(ident, item)
        notes[:] = list(ordered.values())
        back_labels = {
            'en': 'Back to reference {number}, occurrence {occurrence}',
            'ru': 'Вернуться к сноске {number}, упоминание {occurrence}',
            'uk': 'Повернутися до виноски {number}, згадка {occurrence}',
        }
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
            for back in list(paragraph):
                if back.get('class') == 'footnote-backref':
                    paragraph.remove(back)
            if len(refs) > 1:
                paragraph.text = (paragraph.text or '') + '↩ '
            for index, (_, ref_id) in enumerate(refs):
                label = back_labels[self.lang].format(number=number, occurrence=index + 1)
                back = etree.SubElement(paragraph, 'a', {
                    'class': 'footnote-backref', 'href': '#' + ref_id,
                    'aria-label': label, 'title': label,
                })
                back.text = occurrence_label(index) if len(refs) > 1 else '↩'
                back.tail = ' ' if index + 1 < len(refs) else ''
