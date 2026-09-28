"""Unit tests for source selection and safe demo-clip reuse."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_demo_audio", ROOT / "tools/build_demo_audio.py")
assert SPEC is not None and SPEC.loader is not None
BUILD_DEMO_AUDIO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_DEMO_AUDIO)


class BuildDemoAudioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.timings, _ = BUILD_DEMO_AUDIO.source_data()

    def test_committed_timing_fingerprints_match_tsv(self) -> None:
        for narrator, fingerprint in BUILD_DEMO_AUDIO.REUSABLE_TIMING_FINGERPRINTS.items():
            with self.subTest(narrator=narrator):
                self.assertEqual(BUILD_DEMO_AUDIO.timing_fingerprint(narrator, self.timings), fingerprint)

    def test_continuous_clips_cover_all_five_verses(self) -> None:
        records = BUILD_DEMO_AUDIO.recorded_continuous()
        self.assertEqual(set(records), set(BUILD_DEMO_AUDIO.NARRATORS))
        for narrator, record in records.items():
            with self.subTest(narrator=narrator):
                self.assertEqual(BUILD_DEMO_AUDIO.continuous_info(narrator, self.timings), record)
                self.assertEqual(record["intervals"][0]["start"], 0.05)
                self.assertLess(record["intervals"][-1]["end"], record["duration"])

    def test_reused_clips_require_source_when_timings_change(self) -> None:
        narrator = "bsb_souer"
        clips = [{"sha256": str(verse), "duration": float(verse)} for verse in range(1, 6)]
        changed = dict(self.timings)
        begin, end = changed[narrator, 1]
        changed[narrator, 1] = (begin + 1, end + 1)

        with self.assertRaisesRegex(ValueError, rf"{narrator}: timings changed.*{narrator}\.mp3"):
            BUILD_DEMO_AUDIO.validate_reused_clips(narrator, clips, [clips], changed)

    def test_duplicate_narrator_sources_are_rejected(self) -> None:
        narrator = "bsb_souer"
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path = Path(first) / f"{narrator}.mp3"
            second_path = Path(second) / f"{narrator}.mp3"
            first_path.touch()
            second_path.touch()

            with self.assertRaisesRegex(ValueError, rf"{narrator}: found in both.*source is ambiguous"):
                BUILD_DEMO_AUDIO.find_sources([Path(first), Path(second)])


if __name__ == "__main__":
    unittest.main()
