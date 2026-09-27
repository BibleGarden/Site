"""Validated Bible in a year data and server-rendered article calendar."""

from __future__ import annotations

import csv
import html
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import BuildError

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_PATH = ROOT / "tools/data/chapters.tsv"
PLAN_PATH = ROOT / "content/bible-garden/plans/bible-in-a-year.json"
PLAN_ID = "bible-in-a-year"
PLACEHOLDER = '<div data-reading-plan-placeholder="bible-in-a-year"></div>'
MARKER_RE = re.compile(r"^<!-- plan: ([a-z0-9]+(?:-[a-z0-9]+)*) -->$")
PLAN_INTENT_RE = re.compile(r"<!--\s*(?:plan|paln|plna)\b|<!--\s*plan\s*:", re.IGNORECASE)
CHAPTER_COUNTS = (
    50, 40, 27, 36, 34, 24, 21, 4, 31, 24, 22, 25, 29, 36, 10, 13, 10, 42, 150,
    31, 12, 8, 66, 52, 5, 48, 12, 14, 3, 9, 1, 4, 7, 3, 3, 3, 2, 14, 4,
    28, 16, 24, 21, 28, 16, 16, 13, 6, 6, 4, 4, 5, 3, 6, 4, 3, 1, 13, 5, 5, 3, 5, 1, 1, 1, 22,
)
MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
MERGED_PAIRS = {(19, 9), (19, 114), (39, 3)}
# Hebrew interval, followed by the first and last displayed chapter in that interval.
# Equal display endpoints merge chapters; a one-chapter interval may expand to two.
DISPLAY_RULES = {
    "ru": {19: (
        (1, 8, 1, 8), (9, 10, 9, 9), (11, 113, 10, 112),
        (114, 115, 113, 113), (116, 116, 114, 115),
        (117, 146, 116, 145), (147, 147, 146, 147), (148, 150, 148, 150),
    )},
    "uk": {39: ((1, 3, 1, 3), (4, 4, 3, 3))},
}
# The supplied export numbers James–Jude before Romans–Hebrews. Map its IDs to Protestant order.
SOURCE_NT = (
    ("James", 59), ("1 Peter", 60), ("2 Peter", 61), ("1 John", 62), ("2 John", 63),
    ("3 John", 64), ("Jude", 65), ("Romans", 45), ("1 Corinthians", 46),
    ("2 Corinthians", 47), ("Galatians", 48), ("Ephesians", 49), ("Philippians", 50),
    ("Colossians", 51), ("1 Thessalonians", 52), ("2 Thessalonians", 53),
    ("1 Timothy", 54), ("2 Timothy", 55), ("Titus", 56), ("Philemon", 57),
    ("Hebrews", 58), ("Revelation", 66),
)


@dataclass(frozen=True)
class Chapter:
    book: int
    chapter: int
    names: dict[str, str]
    tenths: int


@dataclass(frozen=True)
class ReadingUnit:
    chapters: tuple[Chapter, ...]

    @property
    def tenths(self) -> int:
        return sum(item.tenths for item in self.chapters)


def load_chapters(path: Path = CHAPTERS_PATH) -> list[Chapter]:
    if not path.is_file():
        raise BuildError(f"{path}: missing chapter source")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected = {"book", "full_name_en", "full_name_ru", "full_name_uk", "chapter", "verses", "seconds_bsb_souer"}
        if len(reader.fieldnames or ()) != len(expected) or set(reader.fieldnames or ()) != expected:
            raise BuildError(f"{path}: expected chapter TSV columns {sorted(expected)}")
        chapters = []
        for line_number, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("malformed TSV row")
                source_book = int(row["book"])
                if not 1 <= source_book <= 66:
                    raise ValueError("source book must be 1–66")
                if source_book >= 45:
                    expected_name, book = SOURCE_NT[source_book - 45]
                    if row["full_name_en"] != expected_name:
                        raise ValueError(f"source book {source_book} must be {expected_name}")
                else:
                    book = source_book
                chapter = int(row["chapter"])
                verses = int(row["verses"])
                duration = Decimal(row["seconds_bsb_souer"])
                tenths = duration * 10
                if not tenths.is_finite() or tenths != int(tenths):
                    raise ValueError("duration must have one decimal place")
                if not 1 <= book <= 66 or not 1 <= chapter <= CHAPTER_COUNTS[book - 1] or verses < 1 or tenths <= 0:
                    raise ValueError("invalid book, chapter, verses or duration")
                names = {lang: row[f"full_name_{lang}"].strip() for lang in ("en", "ru", "uk")}
                if not all(names.values()):
                    raise ValueError("empty book name")
            except (ValueError, TypeError, AttributeError, InvalidOperation, KeyError) as error:
                raise BuildError(f"{path}:{line_number}: invalid chapter: {error}") from error
            chapters.append(Chapter(book, chapter, names, int(tenths)))
    chapters.sort(key=lambda item: (item.book, item.chapter))
    expected_order = [(book, chapter) for book, count in enumerate(CHAPTER_COUNTS, 1) for chapter in range(1, count + 1)]
    if [(item.book, item.chapter) for item in chapters] != expected_order:
        raise BuildError(f"{path}: expected all 1189 chapters once in canonical order")
    names_by_book: dict[int, dict[str, str]] = {}
    for item in chapters:
        names = names_by_book.setdefault(item.book, item.names)
        if item.names != names:
            raise BuildError(f"{path}: inconsistent names for book {item.book}")
    return chapters


def streams(chapters: list[Chapter]) -> tuple[list[Chapter], list[Chapter]]:
    a = [item for item in chapters if item.book <= 39 and item.book != 19]
    b = [item for item in chapters if item.book >= 40] + [item for item in chapters if item.book == 19]
    if len(a) != 779 or len(b) != 410:
        raise BuildError("chapter source: expected 779 Old Testament chapters without Psalms and 410 New Testament plus Psalms chapters")
    return a, b


def reading_units(chapters: list[Chapter]) -> list[ReadingUnit]:
    """Keep chapter pairs that share one ru/uk displayed chapter on the same day."""
    units = []
    index = 0
    while index < len(chapters):
        first = chapters[index]
        count = 2 if (first.book, first.chapter) in MERGED_PAIRS else 1
        if count == 2 and (index + 1 == len(chapters) or
                           (chapters[index + 1].book, chapters[index + 1].chapter) != (first.book, first.chapter + 1)):
            raise BuildError(f"chapter source: missing partner for {first.book}:{first.chapter}")
        units.append(ReadingUnit(tuple(chapters[index:index + count])))
        index += count
    return units


def range_data(items: list[Chapter]) -> dict:
    return {
        "start": {"book": items[0].book, "chapter": items[0].chapter},
        "end": {"book": items[-1].book, "chapter": items[-1].chapter},
    }


def validate_plan(data: object, chapters: list[Chapter], path: Path = PLAN_PATH) -> list[dict]:
    if not isinstance(data, dict) or set(data) != {"days"} or not isinstance(data["days"], list) or len(data["days"]) != 365:
        raise BuildError(f"{path}: expected exactly 365 plan days")
    a, b = streams(chapters)
    positions = [0, 0]
    for number, day in enumerate(data["days"], 1):
        if not isinstance(day, dict) or set(day) != {"a", "b", "seconds"}:
            raise BuildError(f"{path}: day {number}: expected a, b and seconds")
        total = 0
        for index, key in enumerate(("a", "b")):
            stream = (a, b)[index]
            start = positions[index]
            if start >= len(stream) or not isinstance(day[key], dict) or set(day[key]) != {"start", "end"}:
                raise BuildError(f"{path}: day {number}: invalid or empty {key} range")
            first = stream[start]
            if day[key]["start"] != {"book": first.book, "chapter": first.chapter}:
                raise BuildError(f"{path}: day {number}: {key} does not start at the next chapter")
            end = day[key]["end"]
            if not isinstance(end, dict) or set(end) != {"book", "chapter"} or type(end["book"]) is not int or type(end["chapter"]) is not int:
                raise BuildError(f"{path}: day {number}: invalid {key} end")
            if (end["book"], end["chapter"]) in MERGED_PAIRS:
                raise BuildError(f"{path}: day {number}: {key} boundary splits a merged chapter unit")
            while positions[index] < len(stream):
                item = stream[positions[index]]
                positions[index] += 1
                total += item.tenths
                if (item.book, item.chapter) == (end["book"], end["chapter"]):
                    break
            else:
                raise BuildError(f"{path}: day {number}: {key} end chapter is missing")
        if (type(day["seconds"]) not in (int, float) or not math.isfinite(day["seconds"])
                or abs(day["seconds"] * 10 - total) > 1e-7):
            raise BuildError(f"{path}: day {number}: incorrect total seconds")
    if positions != [len(a), len(b)]:
        raise BuildError(f"{path}: plan omits chapters")
    return data["days"]


def load_plan(path: Path = PLAN_PATH, chapter_path: Path = CHAPTERS_PATH) -> tuple[list[dict], list[Chapter]]:
    chapters = load_chapters(chapter_path)
    if not path.is_file():
        raise BuildError(f"{path}: missing reading plan; run tools/build_reading_plan.py")
    def unique_keys(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys, parse_constant=reject_constant)
    except (OSError, ValueError) as error:
        raise BuildError(f"{path}: invalid reading plan JSON: {error}") from error
    return validate_plan(data, chapters, path), chapters


def annotate_plan_marker(body: str, source: Path, site: str, body_start_line: int = 1) -> tuple[str, bool]:
    from .content import _fenced_flags

    lines = body.splitlines()
    fenced = _fenced_flags(lines)
    found = False
    for index, line in enumerate(lines):
        if fenced[index] or not PLAN_INTENT_RE.search(line):
            continue
        match = MARKER_RE.fullmatch(line)
        if not match:
            raise BuildError(f"{source}:{body_start_line + index}: expected <!-- plan: bible-in-a-year -->")
        if site != "bible-garden" or match.group(1) != PLAN_ID:
            raise BuildError(f"{source}:{body_start_line + index}: unknown plan {match.group(1)!r} for {site}")
        if found:
            raise BuildError(f"{source}:{body_start_line + index}: duplicate reading plan marker")
        lines[index] = PLACEHOLDER
        found = True
    return "\n".join(lines) + ("\n" if body.endswith("\n") else ""), found


def display_chapter(lang: str, book: int, chapter: int) -> tuple[int, int]:
    """Map one Hebrew-numbered source chapter to inclusive displayed chapters."""
    if lang not in ("en", "ru", "uk") or not 1 <= book <= len(CHAPTER_COUNTS) or not 1 <= chapter <= CHAPTER_COUNTS[book - 1]:
        raise BuildError(f"reading plan: invalid chapter {lang}:{book}:{chapter}")
    rules = DISPLAY_RULES.get(lang, {}).get(book)
    if rules is None:
        return chapter, chapter
    for first, last, shown_first, shown_last in rules:
        if first <= chapter <= last:
            if first == last or shown_first == shown_last:
                result = (shown_first, shown_last)
            elif last - first == shown_last - shown_first:
                shown = shown_first + chapter - first
                result = (shown, shown)
            else:
                raise BuildError(f"reading plan: invalid display rule for {lang}:{book}:{chapter}")
            if result[0] < 1 or result[0] > result[1]:
                raise BuildError(f"reading plan: invalid displayed chapter range for {lang}:{book}:{chapter}")
            return result
    raise BuildError(f"reading plan: missing display rule for {lang}:{book}:{chapter}")


def format_range(value: dict, names: dict[int, str], lang: str) -> str:
    first, last = value["start"], value["end"]
    shown_first = display_chapter(lang, first["book"], first["chapter"])[0]
    shown_last = display_chapter(lang, last["book"], last["chapter"])[1]
    first_name = html.escape(names[first["book"]])
    if first["book"] != last["book"]:
        return f"{first_name} {shown_first} – {html.escape(names[last['book']])} {shown_last}"
    if shown_first > shown_last:
        raise BuildError(f"reading plan: reversed displayed range for {lang}:{first['book']}:{first['chapter']}–{last['chapter']}")
    if shown_first != shown_last:
        return f"{first_name} {shown_first}–{shown_last}"
    return f"{first_name} {shown_first}"


def render_plan(days: list[dict], chapters: list[Chapter], lang: str, strings: dict) -> str:
    required = {"start_date", "print", "day", "date", "reading", "month", "caption", "done"}
    if not isinstance(strings, dict) or set(strings) != required or not all(isinstance(value, str) and value.strip() for value in strings.values()):
        raise BuildError(f"reading plan: missing or invalid translation for {lang}")
    if not re.fullmatch(r"[^{}]*\{n\}[^{}]*", strings["month"]):
        raise BuildError(f"reading plan: month translation for {lang} needs {{n}}")
    if lang not in ("en", "ru", "uk"):
        raise BuildError(f"reading plan: unknown language {lang!r}")
    for book in DISPLAY_RULES.get(lang, {}):
        for chapter in range(1, CHAPTER_COUNTS[book - 1] + 1):
            display_chapter(lang, book, chapter)
    names = {item.book: item.names[lang] for item in chapters}
    out = [f'<section class="reading-plan" lang="{lang}" data-reading-plan="{PLAN_ID}">',
           '<div class="reading-plan-controls">',
           f'<label>{html.escape(strings["start_date"])} <input type="date" class="reading-plan-start-date"></label>',
           f'<button type="button" class="reading-plan-print">{html.escape(strings["print"])}</button>',
           '</div>']
    offset = 0
    for month, length in enumerate(MONTH_LENGTHS, 1):
        try:
            caption = strings["caption"].format(month=month, first=offset + 1, last=offset + length)
        except (KeyError, ValueError) as error:
            raise BuildError(f"reading plan: invalid caption translation for {lang}: {error}") from error
        out.append(f'<details class="reading-plan-month"{" open" if month == 1 else ""}>')
        out.append(f'<summary>{html.escape(strings["month"].format(n=month))}'
                   '<span class="reading-plan-month-dates"></span></summary>')
        out.append(f'<div class="reading-plan-month-body"><table><caption class="sr-only">{html.escape(caption)}</caption><thead><tr>')
        for label in ("day", "date", "reading"):
            out.append(f'<th scope="col">{html.escape(strings[label])}</th>')
        out.append(f'<th scope="col" class="reading-plan-check-heading"><span aria-hidden="true">✓</span>'
                   f'<span class="sr-only">{html.escape(strings["done"])}</span></th></tr></thead><tbody>')
        for day_number in range(offset + 1, offset + length + 1):
            day = days[day_number - 1]
            reading = f'{format_range(day["a"], names, lang)} · {format_range(day["b"], names, lang)}'
            out.append(f'<tr data-day="{day_number}"><th scope="row">{day_number}</th>'
                       f'<td class="reading-plan-date"></td><td class="reading-plan-reading">{reading}</td>'
                       '<td class="reading-plan-checkbox">☐</td></tr>')
        out.append('</tbody></table></div></details>')
        offset += length
    out.append('</section>')
    return "\n".join(out)
