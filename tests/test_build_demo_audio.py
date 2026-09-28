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
