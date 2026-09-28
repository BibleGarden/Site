"""Multi Reading demo source validation, marker syntax and localized article HTML."""

from __future__ import annotations

import copy
import html
import json
import re
import tempfile
import unittest
from pathlib import Path

from sitegen.content import load_site, parse_article
from sitegen.errors import BuildError
from sitegen.multi_reading_demo import DEMOS_DIR, annotate_demo_marker, load_demo, validate_demo

ROOT = Path(__file__).resolve().parent.parent
DEMO_IDS = ("multi-reading", "translation-compare")


class MultiReadingDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = {demo_id: load_demo(demo_id) for demo_id in DEMO_IDS}
        cls.site = load_site(ROOT / "content/bible-garden", ROOT)

    def test_data_rejects_missing_or_invalid_verse_clips(self) -> None:
        for demo_id in DEMO_IDS:
            with self.subTest(demo_id=demo_id):
                data = self.data[demo_id]
                path = DEMOS_DIR / f"{demo_id}.json"
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaisesRegex(BuildError, "missing clip"):
                        validate_demo(data, demo_id, path, static_root=Path(directory))
                changed = copy.deepcopy(data)
                changed["clips"]["bsb_souer"]["verses"][4]["duration"] = -1
                with self.assertRaisesRegex(BuildError, "invalid clip duration"):
                    validate_demo(changed, demo_id, path)
                changed = copy.deepcopy(data)
                changed["clips"]["bsb_souer"]["verses"].pop()
                with self.assertRaisesRegex(BuildError, "five verse clips"):
                    validate_demo(changed, demo_id, path)
                changed = copy.deepcopy(data)
                changed["clips"]["bsb_souer"]["verses"][1]["path"] = changed["clips"]["bsb_souer"]["verses"][0]["path"]
                with self.assertRaisesRegex(BuildError, "invalid clip path"):
                    validate_demo(changed, demo_id, path)
                changed = copy.deepcopy(data)
                changed["clips"]["bsb_souer"]["verses"][0]["sha256"] = "0" * 64
                with self.assertRaisesRegex(BuildError, "checksum mismatch"):
                    validate_demo(changed, demo_id, path)
                changed = copy.deepcopy(data)
                first_translation = next(iter(changed["texts"]))
                changed["texts"][first_translation] = changed["texts"][first_translation][:-1]
                with self.assertRaisesRegex(BuildError, "five nonempty verse texts"):
                    validate_demo(changed, demo_id, path)

    def test_data_rejects_invalid_narrator_pairs_and_names(self) -> None:
        data = self.data["multi-reading"]
        path = DEMOS_DIR / "multi-reading.json"
        changed = copy.deepcopy(data)
        changed["pairs"]["ru"] = [changed["pairs"]["ru"][0], changed["pairs"]["ru"][0]]
        with self.assertRaisesRegex(BuildError, "invalid narrator pair"):
            validate_demo(changed, "multi-reading", path)
        changed = copy.deepcopy(data)
        changed["pairs"]["ru"] = ["unknown-narrator", changed["pairs"]["ru"][1]]
        with self.assertRaisesRegex(BuildError, "invalid narrator pair"):
            validate_demo(changed, "multi-reading", path)
        changed = copy.deepcopy(data)
        changed["clips"]["bsb_souer"]["names"]["ru"] = ["", "Someone"]
        with self.assertRaisesRegex(BuildError, "invalid localized translation or narrator names"):
            validate_demo(changed, "multi-reading", path)

    def test_data_allows_optional_narrator_name(self) -> None:
        data = self.data["translation-compare"]
        self.assertIsNone(data["clips"]["npu_uk"]["names"]["en"][1])
        self.assertIsNone(data["clips"]["npu_uk"]["names"]["ru"][1])
        self.assertIsNone(data["clips"]["npu_uk"]["names"]["uk"][1])

    def test_marker_is_exact_and_unique(self) -> None:
        source = Path("example.md")
        for demo_id in DEMO_IDS:
            with self.subTest(demo_id=demo_id):
                valid, found = annotate_demo_marker(f"Before\n<!-- demo: {demo_id} -->\nAfter", source, "bible-garden", 7)
                self.assertEqual(found, demo_id)
                self.assertIn(f'data-demo-placeholder="{demo_id}"', valid)
        for marker, message in (
            ("<!-- demo: unknown -->", "unknown demo"),
            (" <!-- demo: multi-reading -->", "expected"),
            ("<!-- demo: multi-reading-->", "expected"),
            ("<!-- demo: multi-reading -->\n<!-- demo: multi-reading -->", "duplicate"),
            ("<!-- demo: multi-reading -->\n<!-- demo: translation-compare -->", "duplicate"),
        ):
            with self.subTest(marker=marker), self.assertRaisesRegex(BuildError, message):
                annotate_demo_marker(marker, source, "bible-garden")
        _, found = annotate_demo_marker("```markdown\n<!-- demo: multi-reading -->\n```", source, "bible-garden")
        self.assertIsNone(found)

    def test_article_has_correct_text_pair_in_each_language(self) -> None:
        for demo_id in DEMO_IDS:
            data = self.data[demo_id]
            with self.subTest(demo_id=demo_id), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "demo.md"
                source.write_text(
                    f"---\ntitle: Demo\ndescription: Demo article\ndate: 2026-09-27\n---\n\n<!-- demo: {demo_id} -->\n",
                    encoding="utf-8",
                )
                for lang, narrators in data["pairs"].items():
                    with self.subTest(demo_id=demo_id, lang=lang):
                        article = parse_article(source, "demo", lang, {}, {}, self.site.i18n[lang]["articles"], Path(directory))
                        body = article.body_html
                        first, second = (data["clips"][key] for key in narrators)
                        self.assertTrue(article.has_demo)
                        self.assertIn(html.escape(data["title"][lang]), body)
                        self.assertEqual(body.count('data-verse="'), 5)
                        self.assertIn(data["texts"][first["translation"]][0], body)
                        self.assertIn(data["texts"][second["translation"]][4], body)
                        for clip in (first, second):
                            translation_name, narrator_name = clip["names"][lang]
                            self.assertIn(translation_name, body)
                            if narrator_name is not None:
                                self.assertIn(narrator_name, body)
                        self.assertIn('class="multi-reading-controls" hidden', body)
                        self.assertIn('<audio data-demo-player preload="none"', body)
                        self.assertEqual(body.count('<audio '), 1)
                        self.assertNotIn('<a ', body)
                        self.assertNotIn('data-demo-clip', body)
                        self.assertNotIn('multi-reading-manual', body)
                        paths = json.loads(html.unescape(re.search(r'data-clips="([^"]+)"', body).group(1)))
                        self.assertEqual(paths, [
                            clip["verses"][verse]["path"]
                            for verse in range(5) for clip in (first, second)
                        ])

    def test_translation_compare_pairs_same_language_texts(self) -> None:
        data = self.data["translation-compare"]
        from sitegen.multi_reading_demo import TEXT_LANG

        for lang, narrators in data["pairs"].items():
            first, second = (data["clips"][key] for key in narrators)
            self.assertEqual(TEXT_LANG[first["translation"]], lang)
            self.assertEqual(TEXT_LANG[second["translation"]], lang)
            self.assertNotEqual(first["translation"], second["translation"])

    def test_unknown_demo_id_fails_to_load(self) -> None:
        with self.assertRaisesRegex(BuildError, "missing demo data"):
            load_demo("no-such-demo")


if __name__ == "__main__":
    unittest.main()
