"""Multi Reading source validation, marker syntax and localized article HTML."""

from __future__ import annotations

import copy
import re
import tempfile
import unittest
from pathlib import Path

from sitegen.content import load_site, parse_article
from sitegen.errors import BuildError
from sitegen.multi_reading_demo import annotate_demo_marker, load_demo, validate_demo

ROOT = Path(__file__).resolve().parent.parent


class MultiReadingDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_demo()
        cls.site = load_site(ROOT / "content/bible-garden", ROOT)

    def test_data_rejects_missing_or_invalid_verse_clips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(BuildError, "missing clip"):
                validate_demo(self.data, static_root=Path(directory))
        changed = copy.deepcopy(self.data)
        changed["clips"]["bsb_souer"]["verses"][4]["duration"] = -1
        with self.assertRaisesRegex(BuildError, "invalid clip duration"):
            validate_demo(changed)
        changed = copy.deepcopy(self.data)
        changed["clips"]["bsb_souer"]["verses"].pop()
        with self.assertRaisesRegex(BuildError, "five verse clips"):
            validate_demo(changed)
        changed = copy.deepcopy(self.data)
        changed["clips"]["bsb_souer"]["verses"][1]["path"] = changed["clips"]["bsb_souer"]["verses"][0]["path"]
        with self.assertRaisesRegex(BuildError, "invalid clip path"):
            validate_demo(changed)
        changed = copy.deepcopy(self.data)
        changed["clips"]["bsb_souer"]["verses"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(BuildError, "checksum mismatch"):
            validate_demo(changed)
        changed = copy.deepcopy(self.data)
        changed["texts"]["bti"] = changed["texts"]["bti"][:-1]
        with self.assertRaisesRegex(BuildError, "five nonempty verse texts"):
            validate_demo(changed)

    def test_marker_is_exact_and_unique(self) -> None:
        source = Path("example.md")
        valid, found = annotate_demo_marker("Before\n<!-- demo: multi-reading -->\nAfter", source, "bible-garden", 7)
        self.assertTrue(found)
        self.assertIn('data-demo-placeholder="multi-reading"', valid)
        for marker, message in (
            ("<!-- demo: unknown -->", "unknown demo"),
            (" <!-- demo: multi-reading -->", "expected"),
            ("<!-- demo: multi-reading-->", "expected"),
            ("<!-- demo: multi-reading -->\n<!-- demo: multi-reading -->", "duplicate"),
        ):
            with self.subTest(marker=marker), self.assertRaisesRegex(BuildError, message):
                annotate_demo_marker(marker, source, "bible-garden")
        _, found = annotate_demo_marker("```markdown\n<!-- demo: multi-reading -->\n```", source, "bible-garden")
        self.assertFalse(found)

    def test_article_has_correct_text_pair_in_each_language(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "demo.md"
            source.write_text("---\ntitle: Demo\ndescription: Demo article\ndate: 2026-09-27\n---\n\n<!-- demo: multi-reading -->\n", encoding="utf-8")
            for lang, narrators in self.data["pairs"].items():
                with self.subTest(lang=lang):
                    article = parse_article(source, "demo", lang, {}, {}, self.site.i18n[lang]["articles"], Path(directory))
                    body = article.body_html
                    first, second = (self.data["clips"][key] for key in narrators)
                    self.assertTrue(article.has_demo)
                    self.assertEqual(body.count('data-verse="'), 5)
                    self.assertIn(self.data["texts"][first["translation"]][0], body)
                    self.assertIn(self.data["texts"][second["translation"]][4], body)
                    self.assertIn(first["names"][lang][1], body)
                    self.assertIn(second["names"][lang][1], body)
                    self.assertIn('class="multi-reading-controls" hidden', body)
                    self.assertIn('<audio data-demo-player preload="none"', body)
                    self.assertEqual(body.count('data-demo-clip href='), 10)
                    paths = re.findall(r'data-demo-clip href="([^"]+)"', body)
                    self.assertEqual(paths, [
                        clip["verses"][verse]["path"]
                        for verse in range(5) for clip in (first, second)
                    ])


if __name__ == "__main__":
    unittest.main()
