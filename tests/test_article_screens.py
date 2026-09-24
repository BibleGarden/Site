"""Article screenshot markers and committed asset checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sitegen.content import annotate_screens, extract_faq, render_markdown
from sitegen.errors import BuildError
from sitegen.screens import Screen, check_asset, load_catalog

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "content/bible-garden/articles/template-check/ru.md"


class ArticleScreensTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.screens = load_catalog(ROOT / "content/bible-garden/screens.yaml", ("en", "ru", "uk"))

    def test_markers_render_localized_images_and_preserve_heading_anchor(self) -> None:
        body = "## Выбор перевода {#translation}\n<!-- screen: translation-picker -->\n\nТекст.\n"
        marked, clean, refs = annotate_screens(body, SOURCE, "ru", self.screens)
        html = render_markdown(marked, refs, "Открыть скриншот крупнее: {caption}")
        self.assertIn('id="translation"', html)
        self.assertIn('data-screen="translation-picker"', html)
        self.assertIn('/img/article-screens/mobile/translation-picker.ru.webp', html)
        self.assertIn('alt="Выбор перевода Библии для чтения"', html)
        self.assertIn('/img/article-screens/zoom/translation-picker.ru.webp', html)
        self.assertNotIn("screen:", html)
        self.assertEqual(clean, "## Выбор перевода {#translation}\n\nТекст.\n")

    def test_unknown_or_misplaced_marker_fails_with_source(self) -> None:
        cases = (
            "## Heading\n<!-- screen: missing -->\n",
            "Paragraph\n<!-- screen: home -->\n",
            "## Heading\n\n<!-- screen: home -->\n",
            "## Heading\n<!-- screen: Home -->\n",
        )
        for body in cases:
            with self.subTest(body=body), self.assertRaisesRegex(BuildError, "template-check/ru.md"):
                annotate_screens(body, SOURCE, "ru", self.screens)

    def test_missing_language_variant_fails(self) -> None:
        one_language = {"home": Screen("home", "app", {"en": "Home"})}
        with self.assertRaisesRegex(BuildError, "unknown screen 'home' for language 'ru'"):
            annotate_screens("## Heading\n<!-- screen: home -->\n", SOURCE, "ru", one_language)

    def test_marker_in_fence_is_plain_code_and_faq_still_parses(self) -> None:
        body = "```markdown\n## Heading\n<!-- screen: home -->\n```\n\n## FAQ {#faq}\n<!-- screen: home -->\n\n### Question?\n\nAnswer.\n"
        marked, clean, refs = annotate_screens(body, SOURCE, "ru", self.screens)
        self.assertEqual(len(refs), 1)
        self.assertIn("<!-- screen: home -->", marked)
        self.assertEqual(len(extract_faq(clean, SOURCE)), 1)
        self.assertIn('id="faq"', render_markdown(marked, refs, "Открыть: {caption}"))

    def test_asset_validation_rejects_missing_or_corrupt_webp(self) -> None:
        screen = self.screens["home"]
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with self.assertRaisesRegex(BuildError, "missing screenshot variant"):
                check_asset(screen, "ru", "mobile", output_dir)
            path = output_dir / screen.path("ru", "mobile")
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not a WebP")
            with self.assertRaisesRegex(BuildError, "invalid lossy WebP"):
                check_asset(screen, "ru", "mobile", output_dir)

    def test_catalog_contains_all_accepted_screens(self) -> None:
        self.assertEqual(len(self.screens), 16)
        for screen in self.screens.values():
            for lang in ("en", "ru", "uk"):
                self.assertTrue(screen.captions[lang])
                for variant in ("mobile", "phone", "zoom"):
                    check_asset(screen, lang, variant, ROOT)


if __name__ == "__main__":
    unittest.main()
