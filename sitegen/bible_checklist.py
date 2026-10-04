"""Static, localized chapter checklist with two explicit A4 sheets."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

from .errors import BuildError
from .reading_plan import CHAPTER_COUNTS, SOURCE_NT, display_chapter, load_chapters

MARKER = "<!-- checklist: bible-chapters -->"
PLACEHOLDER = '<div data-checklist-placeholder="bible-chapters"></div>'
INTENT_RE = re.compile(r"<!--\s*(?:checklist|check-list|cheklist|checklsit)\b", re.IGNORECASE)
STRINGS = {
    "en": ("Bible chapter checklist", "66 books · {total} chapters", "Print checklist", "Marks are not saved. Print on two A4 pages.", "Page {page} of 2"),
    "ru": ("Чек-лист глав Библии", "66 книг · {total} глав", "Распечатать чек-лист", "Отметки не сохраняются. Печать на двух страницах A4.", "Страница {page} из 2"),
    "uk": ("Чекліст розділів Біблії", "66 книг · {total} розділів", "Роздрукувати чекліст", "Позначки не зберігаються. Друк на двох сторінках A4.", "Сторінка {page} з 2"),
}


def annotate_checklist_marker(body: str, source: Path, site: str, body_start_line: int = 1) -> tuple[str, bool]:
    from .content import _fenced_flags

    lines = body.splitlines()
    fenced = _fenced_flags(lines)
    found = False
    for index, line in enumerate(lines):
        if fenced[index] or not INTENT_RE.search(line):
            continue
        if line != MARKER:
            raise BuildError(f"{source}:{body_start_line + index}: expected {MARKER}")
        if site != "bible-garden":
            raise BuildError(f"{source}:{body_start_line + index}: checklist is only supported on bible-garden")
        if found:
            raise BuildError(f"{source}:{body_start_line + index}: duplicate checklist marker")
        lines[index], found = PLACEHOLDER, True
    return "\n".join(lines) + ("\n" if body.endswith("\n") else ""), found


VOID_ELEMENTS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})


class _PlaceholderDepth(HTMLParser):
    """Records the element nesting depth at which the checklist placeholder opens."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.placeholder_depths: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if ("data-checklist-placeholder", "bible-chapters") in attrs:
            self.placeholder_depths.append(self.depth)
        if tag not in VOID_ELEMENTS:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag not in VOID_ELEMENTS:
            self.depth -= 1


def require_top_level(body_html: str, source: Path) -> None:
    """Print CSS hides every other child of .article-body, so the checklist must be one of those children."""
    parser = _PlaceholderDepth()
    parser.feed(body_html)
    parser.close()
    if parser.placeholder_depths != [0]:
        raise BuildError(f"{source}: checklist marker must be a top-level block of the article, "
                         "not inside an HTML wrapper (print would hide it)")


def checklist_books(lang: str) -> list[tuple[int, str, list[int]]]:
    if lang not in STRINGS:
        raise BuildError(f"checklist: unsupported language {lang!r}")
    names = {chapter.book: chapter.names[lang] for chapter in load_chapters()}
    order = list(range(1, 67))
    if lang == "ru":
        order = list(range(1, 45)) + [book for _, book in SOURCE_NT]
    books = []
    for book in order:
        displayed = set()
        for chapter in range(1, CHAPTER_COUNTS[book - 1] + 1):
            first, last = display_chapter(lang, book, chapter)
            displayed.update(range(first, last + 1))
        books.append((book, names[book], sorted(displayed)))
    return books


def render_checklist(lang: str) -> str:
    books = checklist_books(lang)
    title, scope, print_label, note, page_label = STRINGS[lang]
    total = sum(len(chapters) for _, _, chapters in books)
    parts = ['<section class="bible-checklist" aria-label="' + html.escape(title, quote=True) + '">',
             '<div class="checklist-controls"><button type="button" class="checklist-print" hidden>' + print_label + '</button><p>' + note + '</p></div>']
    # Split after Psalms: complete books stay on one sheet, in reading order.
    for page, sheet in enumerate((books[:19], books[19:]), 1):
        parts.append(f'<section class="checklist-sheet" aria-labelledby="checklist-title-{page}">'
                     f'<header><h2 id="checklist-title-{page}">{title}</h2>'
                     f'<p>{scope.format(total=total)} · {page_label.format(page=page)} · bible.garden</p></header>'
                     '<div class="checklist-books">')
        for book, name, chapters in sheet:
            parts.append(f'<section class="checklist-book" data-book="{book}" aria-labelledby="checklist-book-{book}">'
                         f'<h3 id="checklist-book-{book}">{html.escape(name)}</h3><div class="checklist-chapters">')
            for chapter in chapters:
                parts.append(f'<label><input type="checkbox" autocomplete="off" aria-label="{html.escape(name, quote=True)} {chapter}"><span>{chapter}</span></label>')
            parts.append('</div></section>')
        parts.append('</div></section>')
    parts.append('</section>')
    return "".join(parts)
