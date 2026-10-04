"""Validate the editorial chapter sequence, independently of day partitioning."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tools/data"
# TSV export IDs: James–Jude precede Romans–Hebrews. These are USFM IDs,
# not localized display names or the generator's remapped canonical IDs.
SOURCE_CODES = (
    "GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST "
    "JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM "
    "HAB ZEP HAG ZEC MAL MAT MRK LUK JHN ACT JAS 1PE 2PE 1JN 2JN 3JN JUD "
    "ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB REV"
).split()
ADJACENT_PAIRS = (("PSA", 9, 10), ("PSA", 114, 115), ("MAL", 3, 4))


def chapter_inventory() -> set[tuple[str, int]]:
    with (DATA / "chapters.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    inventory = set()
    for row in rows:
        book = int(row["book"])
        if not 1 <= book <= len(SOURCE_CODES):
            raise ValueError(f"invalid TSV book ID: {book}")
        key = (SOURCE_CODES[book - 1], int(row["chapter"]))
        if key in inventory or key[1] < 1:
            raise ValueError(f"invalid/duplicate TSV chapter: {key}")
        inventory.add(key)
    if len(inventory) != 1189 or len({book for book, _ in inventory}) != 66:
        raise ValueError("TSV must contain 1189 chapters in 66 books")
    for book in SOURCE_CODES:
        numbers = {chapter for code, chapter in inventory if code == book}
        if numbers != set(range(1, max(numbers) + 1)):
            raise ValueError(f"TSV chapter gap in {book}")
    return inventory


def validate_sequence(data: dict, decisions: str) -> list[tuple[str, int]]:
    if type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("unsupported sequence version")
    scheme = data.get("chapter_scheme")
    if scheme != {"id": "hebrew-bsb", "chapters": 1189, "books": 66, "unit": "whole-chapter"}:
        raise ValueError("incorrect chapter scheme")
    inventory = chapter_inventory()
    decision_rows = re.findall(r"^\| (D\d{2}) \|", decisions, re.MULTILINE)
    if len(decision_rows) != len(set(decision_rows)) or not decision_rows:
        raise ValueError("empty/duplicate decision IDs")
    decision_ids = set(decision_rows)
    sources = data.get("sources_compared", [])
    source_ids = {source["id"] for source in sources}
    if len(source_ids) != len(sources) or len(source_ids) < 3:
        raise ValueError("expected at least three distinct compared sources")
    eras = {era["id"] for era in data.get("eras", [])}
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("sequence must contain segments")
    expanded = []
    referenced = set()
    for index, segment in enumerate(segments, 1):
        book, first, last = (segment.get(key) for key in ("book", "first", "last"))
        if book not in SOURCE_CODES:
            raise ValueError(f"segment {index}: invalid USFM book {book!r}")
        if type(first) is not int or type(last) is not int or not 1 <= first <= last:
            raise ValueError(f"segment {index}: invalid chapter range")
        if segment.get("era") not in eras:
            raise ValueError(f"segment {index}: unknown era")
        if "decision_id" in segment:
            decision_id = segment["decision_id"]
            if decision_id not in decision_ids:
                raise ValueError(f"segment {index}: unknown decision {decision_id}")
            referenced.add(decision_id)
        support = segment.get("supported_by")
        if not isinstance(support, list) or len(support) != len(set(support)) or set(support) - source_ids:
            raise ValueError(f"segment {index}: invalid source support")
        if not support and "decision_id" not in segment:
            raise ValueError(f"segment {index}: unsupported placement needs a decision")
        for chapter in range(first, last + 1):
            key = (book, chapter)
            if key not in inventory:
                raise ValueError(f"segment {index}: chapter outside inventory {key}")
            expanded.append(key)
    counts = Counter(expanded)
    duplicates = sorted(key for key, count in counts.items() if count != 1)
    missing = sorted(inventory - counts.keys())
    if duplicates or missing or len(expanded) != 1189:
        raise ValueError(f"chapter coverage: missing={missing}, duplicates={duplicates}")
    if referenced != decision_ids:
        raise ValueError(f"unreferenced decisions: {sorted(decision_ids - referenced)}")
    expected_pairs = [{"book": book, "first": first, "last": last} for book, first, last in ADJACENT_PAIRS]
    if data.get("same_day_pairs") != expected_pairs:
        raise ValueError("same-day pair metadata must preserve all translation constraints")
    positions = {key: index for index, key in enumerate(expanded)}
    for book, first, last in ADJACENT_PAIRS:
        if positions[(book, last)] != positions[(book, first)] + 1:
            raise ValueError(f"adjacency constraint violated: {book} {first}+{last}")
    return expanded


def main() -> None:
    data = json.loads((DATA / "chronological-sequence.json").read_text(encoding="utf-8"))
    decisions = (DATA / "chronological-decisions.md").read_text(encoding="utf-8")
    expanded = validate_sequence(data, decisions)
    print(f"Validated {len(expanded)} chapters, 66 books, {len(data['segments'])} segments; all three pairs adjacent.")


if __name__ == "__main__":
    main()
