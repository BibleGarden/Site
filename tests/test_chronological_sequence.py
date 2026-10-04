"""Coverage and failure cases for the data-only chronological sequence."""

from __future__ import annotations

import copy
import json
import unittest

from tools.validate_chronological_sequence import ADJACENT_PAIRS, DATA, validate_sequence


class ChronologicalSequenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads((DATA / "chronological-sequence.json").read_text(encoding="utf-8"))
        cls.decisions = (DATA / "chronological-decisions.md").read_text(encoding="utf-8")

    def test_committed_sequence_covers_inventory_once(self) -> None:
        chapters = validate_sequence(self.data, self.decisions)
        self.assertEqual(len(chapters), 1189)
        self.assertEqual(len(set(chapters)), 1189)
        self.assertEqual(len({book for book, _ in chapters}), 66)
        self.assertEqual(chapters[0], ("GEN", 1))
        self.assertEqual(chapters[-1], ("REV", 22))

    def test_rejects_missing_and_duplicate_chapters(self) -> None:
        for operation in ("missing", "duplicate"):
            data = copy.deepcopy(self.data)
            if operation == "missing":
                data["segments"][0]["first"] = 2
            else:
                data["segments"].append(copy.deepcopy(data["segments"][0]))
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, "chapter coverage"):
                validate_sequence(data, self.decisions)

    def test_rejects_invalid_books_ranges_and_references(self) -> None:
        cases = (
            ("book", "Ge", "invalid USFM"),
            ("first", 0, "invalid chapter range"),
            ("first", True, "invalid chapter range"),
            ("first", 51, "invalid chapter range"),
            ("last", 51, "outside inventory"),
            ("last", "50", "invalid chapter range"),
            ("era", "unknown", "unknown era"),
            ("decision_id", "D99", "unknown decision"),
            ("supported_by", ["crossway"], "invalid source support"),
            ("supported_by", [], "needs a decision"),
        )
        for field, value, message in cases:
            data = copy.deepcopy(self.data)
            data["segments"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, message):
                validate_sequence(data, self.decisions)

    def test_rejects_broken_adjacency_without_changing_coverage(self) -> None:
        for book, first, last in ADJACENT_PAIRS:
            data = copy.deepcopy(self.data)
            # Split into singleton segments, then move one of the pair's
            # chapters. Coverage still passes; adjacency must fail separately.
            data["segments"] = [
                dict(segment, first=chapter, last=chapter)
                for segment in data["segments"]
                for chapter in range(segment["first"], segment["last"] + 1)
            ]
            index = next(
                index for index, segment in enumerate(data["segments"])
                if (segment["book"], segment["first"]) == (book, last)
            )
            data["segments"][index], data["segments"][index + 1] = (
                data["segments"][index + 1], data["segments"][index]
            )
            with self.subTest(book=book, first=first), self.assertRaisesRegex(ValueError, "adjacency"):
                validate_sequence(data, self.decisions)

    def test_rejects_missing_pair_metadata_and_dangling_decisions(self) -> None:
        data = copy.deepcopy(self.data)
        data["same_day_pairs"].pop()
        with self.assertRaisesRegex(ValueError, "same-day pair metadata"):
            validate_sequence(data, self.decisions)
        with self.assertRaisesRegex(ValueError, "unreferenced decisions"):
            validate_sequence(self.data, self.decisions + "\n| D99 | Extra decision |\n")


if __name__ == "__main__":
    unittest.main()
