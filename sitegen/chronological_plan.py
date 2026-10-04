"""Approved chapter sequence and ordered, duration-checked calendar readings."""

from __future__ import annotations

from pathlib import Path

from tools.validate_chronological_sequence import SOURCE_CODES, validate_sequence

from .errors import BuildError
from .reading_plan import (
    CHAPTER_COUNTS, CHRONOLOGICAL_PLAN_ID, MERGED_PAIRS, ROOT, SOURCE_NT, Chapter, _load_plan_json,
    _validate_seconds, load_chapters,
)

SEQUENCE_PATH = ROOT / "tools/data/chronological-sequence.json"
DECISIONS_PATH = ROOT / "tools/data/chronological-decisions.md"
PLAN_ID = CHRONOLOGICAL_PLAN_ID
PLAN_PATH = ROOT / f"content/bible-garden/plans/{PLAN_ID}.json"
PLACEHOLDER = f'<div data-reading-plan-placeholder="{PLAN_ID}"></div>'
BOOK_CODES = {
    code: SOURCE_NT[index - 44][1] if index >= 44 else index + 1
    for index, code in enumerate(SOURCE_CODES)
}


def load_sequence(chapters: list[Chapter], path: Path = SEQUENCE_PATH) -> list[Chapter]:
    data = _load_plan_json(path)
    if not isinstance(data, dict):
        raise BuildError(f"{path}: chronological sequence must be a JSON object")
    try:
        expanded = validate_sequence(data, DECISIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise BuildError(f"{path}: invalid chronological sequence: {error}") from error
    inventory = {(chapter.book, chapter.chapter): chapter for chapter in chapters}
    try:
        return [inventory[(BOOK_CODES[book], chapter)] for book, chapter in expanded]
    except KeyError as error:
        raise BuildError(f"{path}: sequence chapter missing from audio inventory: {error}") from error


def compress_readings(chapters: list[Chapter]) -> list[dict]:
    """Compress only adjacent ascending chapters of the same book."""
    readings = []
    for chapter in chapters:
        if readings and readings[-1]["book"] == chapter.book and readings[-1]["last"] + 1 == chapter.chapter:
            readings[-1]["last"] = chapter.chapter
        else:
            readings.append({"book": chapter.book, "first": chapter.chapter, "last": chapter.chapter})
    return readings


def validate_plan(data: object, stream: list[Chapter], path: Path = PLAN_PATH) -> list[dict]:
    if not isinstance(data, dict) or set(data) != {"days"} or not isinstance(data["days"], list) or len(data["days"]) != 365:
        raise BuildError(f"{path}: expected exactly 365 chronological plan days")
    position = 0
    for number, day in enumerate(data["days"], 1):
        if not isinstance(day, dict) or set(day) != {"readings", "seconds"} or not isinstance(day["readings"], list) or not day["readings"]:
            raise BuildError(f"{path}: day {number}: expected non-empty readings and seconds")
        total = 0
        previous = None
        for reading in day["readings"]:
            if not isinstance(reading, dict) or set(reading) != {"book", "first", "last"} or any(type(reading[key]) is not int for key in reading):
                raise BuildError(f"{path}: day {number}: invalid chapter range")
            book, first, last = (reading[key] for key in ("book", "first", "last"))
            if not 1 <= book <= 66 or not 1 <= first <= last <= CHAPTER_COUNTS[book - 1]:
                raise BuildError(f"{path}: day {number}: invalid book/chapter bounds")
            if previous and previous["book"] == book and previous["last"] + 1 == first:
                raise BuildError(f"{path}: day {number}: adjacent readings must be compressed")
            for chapter in range(first, last + 1):
                if position >= len(stream) or (stream[position].book, stream[position].chapter) != (book, chapter):
                    raise BuildError(f"{path}: day {number}: reading differs from chronological sequence")
                total += stream[position].tenths
                position += 1
            previous = reading
        if (stream[position - 1].book, stream[position - 1].chapter) in MERGED_PAIRS:
            raise BuildError(f"{path}: day {number}: boundary splits a merged chapter unit")
        _validate_seconds(day["seconds"], total, path, number)
    if position != len(stream):
        raise BuildError(f"{path}: chronological plan omits chapters")
    return data["days"]


def load_plan(path: Path = PLAN_PATH) -> tuple[list[dict], list[Chapter]]:
    chapters = load_chapters()
    return validate_plan(_load_plan_json(path), load_sequence(chapters), path), chapters
