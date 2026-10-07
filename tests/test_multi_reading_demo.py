"""Multi Reading demo source validation, marker syntax and localized article HTML."""

from __future__ import annotations

import copy
import html
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from sitegen.content import load_site, parse_article
from sitegen.errors import BuildError
from sitegen.demo_markers import annotate_demo_marker
from sitegen.multi_reading_demo import DEMOS_DIR, load_demo, validate_demo

ROOT = Path(__file__).resolve().parent.parent
DEMO_IDS = ("multi-reading", "translation-compare", "ukrainian-bible", "narrators")
PAIR_DEMOS = ("multi-reading", "translation-compare", "ukrainian-bible")


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
                with self.assertRaisesRegex(BuildError, "5 verse clips"):
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
                with self.assertRaisesRegex(BuildError, "5 nonempty verse texts"):
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
        for demo_id in PAIR_DEMOS:
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
                        self.assertNotIn('aria-pressed', body)
                        self.assertEqual(body.count('data-demo-status aria-live="polite"'), 1)
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

    def test_voices_rows_and_rendering(self) -> None:
        data = self.data["narrators"]
        expected = {
            "ru": ["bondarenko", "prudovsky", "prozorovsky"],
            "en": ["bsb_souer", "bsb_david", "winfred_henson", "web_british"],
            "uk": ["kozlov_uk", "npu_uk"],
        }
        self.assertEqual(data["kind"], "voices")
        for lang, narrators in expected.items():
            self.assertEqual([row["narrator"] for row in data["rows"][lang]], narrators)
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "demo.md"
                source.write_text("---\ntitle: Demo\ndescription: Demo article\ndate: 2026-09-28\n---\n\n<!-- demo: narrators -->\n", encoding="utf-8")
                article = parse_article(source, "demo", lang, {}, {}, self.site.i18n[lang]["articles"], Path(directory))
                body = article.body_html
                self.assertEqual(body.count('data-demo-track'), len(narrators))
                self.assertEqual(body.count('data-voice-passage'), len(narrators))
                self.assertEqual(body.count('data-verse="'), len(narrators) * 5)
                self.assertEqual(body.count('<sup>'), len(narrators) * 5)
                self.assertEqual(body.count('data-intervals="'), len(narrators))
                self.assertNotIn('aria-pressed', body)
                self.assertEqual(body.count('data-demo-status aria-live="polite"'), 1)
                self.assertEqual(body.count('class="multi-reading-controls" hidden'), len(narrators))
                self.assertEqual(body.count('<audio '), 1)
                passages = re.findall(r'<p class="voices-passage" data-voice-passage[^>]*>(.*?)</p>', body, re.S)
                self.assertEqual(len(passages), len(narrators))
                for row, passage in zip(data["rows"][lang], passages):
                    clip = data["clips"][row["narrator"]]
                    self.assertIn(html.escape(row["note"]), body)
                    self.assertIn(clip["continuous"]["path"], body)
                    self.assertEqual(passage.count('data-verse="'), 5)
                    self.assertIn(html.escape(data["texts"][clip["translation"]][4]), passage)
                self.assertNotIn('voices-transcripts', body)
                self.assertNotIn('data-voice-passage hidden', body)
                if lang == "en":
                    self.assertIn("World English Bible, British Edition (WEBBE)", body)
                    self.assertNotIn("None", body)

    def test_voices_schema_rejects_invalid_rows(self) -> None:
        data = self.data["narrators"]
        path = DEMOS_DIR / "narrators.json"
        for change in ("missing-note", "duplicate", "unknown-kind", "extra-field",
                       "continuous-path", "continuous-hash", "interval-overlap"):
            invalid = copy.deepcopy(data)
            if change == "missing-note":
                del invalid["rows"]["ru"][0]["note"]
            elif change == "duplicate":
                invalid["rows"]["ru"][1]["narrator"] = invalid["rows"]["ru"][0]["narrator"]
            elif change == "unknown-kind":
                invalid["kind"] = "other"
            elif change == "continuous-path":
                invalid["clips"]["bsb_souer"]["continuous"]["path"] = "/audio/demo/bsb_souer/1.mp3"
            elif change == "continuous-hash":
                invalid["clips"]["bsb_souer"]["continuous"]["sha256"] = "0" * 64
            elif change == "interval-overlap":
                intervals = invalid["clips"]["bsb_souer"]["continuous"]["intervals"]
                intervals[1]["start"] = intervals[0]["end"] - 0.1
            else:
                invalid["unexpected"] = True
            with self.subTest(change=change), self.assertRaises(BuildError):
                validate_demo(invalid, "narrators", path)

    def test_psalm_demos_render_six_verses_in_their_language(self) -> None:
        expected = {
            "ru": ["prudovsky", "bondarenko", "prozorovsky"],
            "en": ["bsb_souer", "bsb_david", "winfred_henson", "web_british"],
            "uk": ["kozlov_uk", "npu_uk"],
        }
        for lang, narrators in expected.items():
            demo_id = f"psalm23-voices-{lang}"
            data = load_demo(demo_id)
            self.assertEqual(list(data["rows"]), [lang])
            self.assertEqual([row["narrator"] for row in data["rows"][lang]], narrators)
            self.assertEqual(data["passages"]["book"], 19)
            self.assertEqual(data["passages"]["verses"], list(range(1, 7)))
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "demo.md"
                source.write_text(f"---\ntitle: Demo\ndescription: Demo article\ndate: 2026-10-04\n---\n\n<!-- demo: {demo_id} -->\n")
                body = parse_article(source, "demo", lang, {}, {}, self.site.i18n[lang]["articles"], Path(directory)).body_html
                self.assertEqual(body.count('data-demo-track'), len(narrators))
                self.assertEqual(body.count('data-verse="'), 6 * len(narrators))
                self.assertEqual(body.count('class="multi-reading-controls" hidden'), len(narrators))
                self.assertEqual(body.count('data-demo-status aria-live="polite"'), 1)
                self.assertNotIn('aria-pressed', body)
                self.assertNotIn('The Lord Is My Shepherd', body)
                self.assertNotRegex(body, r'<p class="voices-passage"[^>]* hidden')
                for narrator in narrators:
                    clip = data["clips"][narrator]
                    self.assertIn(clip["continuous"]["path"], body)
                    for text in data["texts"][clip["translation"]]:
                        self.assertIn(html.escape(text), body)
                other_lang = "en" if lang != "en" else "ru"
                with self.assertRaisesRegex(BuildError, "no rows for language"):
                    parse_article(source, "demo", other_lang, {}, {}, self.site.i18n[other_lang]["articles"], Path(directory))

    def test_passage_schema_rejects_invalid_metadata_and_intervals(self) -> None:
        demo_id = "psalm23-voices-uk"
        data = load_demo(demo_id)
        for field, value in (("book", True), ("book", 0), ("chapters", {}),
                             ("chapters", {"ubh": 23, "npu": True}),
                             ("verses", []), ("verses", [1, 3]), ("verses", [True, 2]),
                             ("audio_dir", "../psalm23")):
            changed = copy.deepcopy(data)
            changed["passages"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(BuildError):
                validate_demo(changed, demo_id, DEMOS_DIR / f"{demo_id}.json")
        changed = copy.deepcopy(data)
        changed["clips"]["npu_uk"]["continuous"]["intervals"].pop()
        with self.assertRaisesRegex(BuildError, "expected 6 verse intervals"):
            validate_demo(changed, demo_id, DEMOS_DIR / f"{demo_id}.json")

    def test_player_sequences_for_john_and_psalm(self) -> None:
        subprocess.run(["node", str(ROOT / "tests/multi_reading_demo_sequence.js")],
                       cwd=ROOT, check=True, capture_output=True, text=True)

    def test_unknown_demo_id_fails_to_load(self) -> None:
        with self.assertRaisesRegex(BuildError, "missing demo data"):
            load_demo("no-such-demo")


if __name__ == "__main__":
    unittest.main()
