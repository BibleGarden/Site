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

    def test_dated_editorial_anchors_follow_their_narrative_context(self) -> None:
        chapters = validate_sequence(self.data, self.decisions)
        positions = {chapter: index for index, chapter in enumerate(chapters)}
        constraints = (
            (("DAN", 3), ("2KI", 24)),
            (("2KI", 24), ("JER", 24)),
            (("EZR", 3), ("DAN", 10)),
            (("DAN", 12), ("EZR", 4)),
            (("NEH", 11), ("1CH", 9)),
            (("1CH", 9), ("NEH", 12)),
            (("MAT", 3), ("JHN", 1)),
            (("LUK", 3), ("JHN", 1)),
            (("JHN", 4), ("MRK", 1)),
            (("JHN", 5), ("MRK", 2)),
            (("MRK", 9), ("LUK", 9)),
            (("2CO", 13), ("ROM", 1)),
            (("ROM", 16), ("ACT", 20)),
            (("2CH", 28), ("ISA", 7)),
            (("2CH", 28), ("MIC", 1)),
            (("1KI", 1), ("1CH", 23)),
            (("1CH", 29), ("1KI", 2)),
            (("2CH", 34), ("ZEP", 1)),
            (("ZEP", 3), ("2KI", 23)),
            (("JER", 6), ("2KI", 23)),
        )
        for earlier, later in constraints:
            with self.subTest(earlier=earlier, later=later):
                self.assertLess(positions[earlier], positions[later])
        self.assertEqual(positions[("PSA", 56)], positions[("PSA", 34)] + 1)
        self.assertEqual(positions[("ISA", 40)], positions[("ISA", 39)] + 1)

    def test_anthologies_are_undated_and_split_across_contexts(self) -> None:
        anthologies = [s for s in self.data["segments"] if s.get("placement_kind") == "undated-anthology"]
        self.assertTrue(anthologies)
        self.assertEqual({s["era"] for s in anthologies}, {"united-monarchy", "exile-return"})
        for segment in anthologies:
            self.assertEqual(segment["supported_by"], [])
            self.assertEqual(segment["decision_id"], "D07")
        chapters = validate_sequence(self.data, self.decisions)
        positions = {chapter: index for index, chapter in enumerate(chapters)}
        for chapter, anchor in ((1, ("1CH", 29)), (73, ("LAM", 5)), (91, ("NEH", 13))):
            self.assertGreater(positions[("PSA", chapter)], positions[anchor])

    def test_rejects_ambiguous_scheme_and_unexplained_source_support(self) -> None:
        data = copy.deepcopy(self.data)
        data["chapter_scheme"]["id"] = "hebrew-bsb"
        with self.assertRaisesRegex(ValueError, "chapter scheme"):
            validate_sequence(data, self.decisions)
        data = copy.deepcopy(self.data)
        data["segments"][0].pop("support_basis")
        with self.assertRaisesRegex(ValueError, "explicit basis"):
            validate_sequence(data, self.decisions)


if __name__ == "__main__":
    unittest.main()
