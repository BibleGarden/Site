"""Article screenshot markers and committed asset checks."""

from __future__ import annotations

import re
import subprocess
from dataclasses import replace
from xml.etree import ElementTree as ET
import tempfile
import unittest
from pathlib import Path

from sitegen.build import SiteBuilder, build_all
from sitegen.content import annotate_screens, extract_faq, parse_article, render_markdown
from sitegen.errors import BuildError
from sitegen.screens import Screen, check_asset, load_catalog, load_checksums

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "content/bible-garden/articles/template-check/ru.md"


class ArticleScreensTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.screens = load_catalog(ROOT / "content/bible-garden/screens.yaml", ("en", "ru", "uk"))
        cls.checksums = load_checksums(ROOT / "content/bible-garden/screens.sha256", cls.screens, ("en", "ru", "uk"))

    def test_markers_render_localized_images_and_preserve_heading_anchor(self) -> None:
        body = "## Выбор перевода {#translation}\n<!-- screen: translation-picker -->\n\nТекст.\n"
        marked, clean, refs = annotate_screens(body, SOURCE, "ru", self.screens)
        html = render_markdown(marked, refs, "Открыть скриншот крупнее: {caption}")
        self.assertIn('id="translation"', html)
        self.assertIn('data-screen="translation-picker"', html)
        self.assertIn('/img/article-screens/mobile/translation-picker.ru.webp', html)
        self.assertIn('/img/article-screens/phone/translation-picker.ru.webp 480w', html)
        self.assertIn('sizes="180px"', html)
        self.assertIn('alt="Выбор перевода Библии для чтения"', html)
        self.assertIn('/img/article-screens/zoom/translation-picker.ru.webp', html)
        self.assertNotIn("article-screen-app-label", html)
        self.assertNotIn("screen:", html)
        self.assertEqual(clean, "## Выбор перевода {#translation}\n\nТекст.\n")

    def test_catalog_app_default_and_strict_validation(self) -> None:
        self.assertEqual(self.screens["home"].app, "bible-garden")
        for screen_id in ("lampada-journal", "lampada-question"):
            self.assertEqual(self.screens[screen_id].app, "lampada")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "screens.yaml"
            for value in ("bible-garden", "lampada"):
                path.write_text(f"home:\n  kind: app\n  app: {value}\n  captions: {{ru: Home}}\n", encoding="utf-8")
                self.assertEqual(load_catalog(path, ("ru",))["home"].app, value)
            for value in ("unknown", "null", "false", "1", "[]", "{}", "''"):
                path.write_text(f"home:\n  kind: app\n  app: {value}\n  captions: {{ru: Home}}\n", encoding="utf-8")
                with self.subTest(value=value), self.assertRaisesRegex(BuildError, "unknown app"):
                    load_catalog(path, ("ru",))
            path.write_text("home:\n  kind: app\n  captions: {ru: Home}\n  extra: true\n", encoding="utf-8")
            with self.assertRaisesRegex(BuildError, "optional app"):
                load_catalog(path, ("ru",))

    def test_lampada_mobile_label_requires_translation(self) -> None:
        marked, _, refs = annotate_screens("## Journal\n<!-- screen: lampada-journal -->\n", SOURCE, "ru", self.screens)
        for label in ("", " ", None):
            with self.subTest(label=label), self.assertRaisesRegex(BuildError, "missing articles.screen_app_lampada"):
                render_markdown(marked, refs, "Open: {caption}", label)

    def test_lampada_labels_render_in_all_languages_and_first_screen_without_js(self) -> None:
        labels = {
            "ru": "Lampada — наше второе приложение",
            "en": "Lampada — our second app",
            "uk": "Lampada — наш другий застосунок",
        }
        with tempfile.TemporaryDirectory() as directory:
            builder = SiteBuilder(ROOT / "content/bible-garden", Path(directory) / "bible-garden", preview=True)
            for lang, label in labels.items():
                marked, _, refs = annotate_screens(
                    "## Journal\n<!-- screen: lampada-journal -->\n\n## Home\n<!-- screen: home -->\n\n## Question\n<!-- screen: lampada-question -->\n",
                    SOURCE, lang, self.screens,
                )
                body = render_markdown(marked, refs, builder.t(lang)["articles"]["screen_open"], builder.t(lang)["articles"]["screen_app_lampada"])
                figures = ET.fromstring(f"<div>{body}</div>").findall("figure")
                self.assertEqual([len(figure.findall("figcaption")) for figure in figures], [1, 0, 1])
                for figure in (figures[0], figures[2]):
                    self.assertEqual(figure.find("figcaption/span").text, label)
                    self.assertEqual(figure.find("figcaption/img").get("alt"), "")
                    self.assertEqual(figure.find("figcaption/img").get("src"), "/img/lampada-icon-64.png")
                article = builder.articles["template-check"][lang]
                builder.articles["template-check"][lang] = replace(article, screens=refs, body_html=body)
                builder.build_article("template-check", lang)
                html = builder.output_path(lang, "articles/template-check/index.html").read_text(encoding="utf-8")
                self.assertEqual(html.count(label), 3)
                self.assertIn('class="article-screen-app-label">', html)
                self.assertNotIn('class="article-screen-app-label" hidden', html)
                self.assertIn('data-app="lampada" data-src="/img/article-screens/phone/lampada-journal.', html)
                self.assertIn('<noscript><img class="article-screen-noscript" src="/img/article-screens/phone/lampada-journal.', html)
            self.assertEqual((builder.site.output_dir / "img/lampada-icon-64.png").read_bytes(), (ROOT / "static/lampada/assets/lampada-icon-64.png").read_bytes())

    def test_pager_uses_unique_screens_in_article_order_and_localized_buttons(self) -> None:
        labels = {
            "en": ("Previous screen", "Next screen", "Screen {n} of 3"),
            "ru": ("Предыдущий экран", "Следующий экран", "Экран {n} из 3"),
            "uk": ("Попередній екран", "Наступний екран", "Екран {n} із 3"),
        }
        with tempfile.TemporaryDirectory() as directory:
            builder = SiteBuilder(ROOT / "content/bible-garden", Path(directory) / "bible-garden", preview=True)
            for lang, (previous, following, position) in labels.items():
                marked, _, refs = annotate_screens(
                    "## Home\n<!-- screen: home -->\n\n## Journal\n<!-- screen: lampada-journal -->\n"
                    "\n## Home again\n<!-- screen: home -->\n\n## Question\n<!-- screen: lampada-question -->\n",
                    SOURCE, lang, self.screens,
                )
                body = render_markdown(
                    marked, refs, builder.t(lang)["articles"]["screen_open"],
                    builder.t(lang)["articles"]["screen_app_lampada"],
                )
                article = builder.articles["template-check"][lang]
                for selected_refs, count in ((refs, 3), (refs[:1] * 2, 0), ((), 0)):
                    with self.subTest(lang=lang, screens=len(selected_refs)):
                        builder.articles["template-check"][lang] = replace(
                            article, screens=selected_refs, body_html=body,
                        )
                        builder.build_article("template-check", lang)
                        html = builder.output_path(lang, "articles/template-check/index.html").read_text(encoding="utf-8")
                        self.assertEqual(html.count('class="article-screen-dot"'), count)
                        if not count:
                            self.assertNotIn('class="article-screen-pager"', html)
                            continue
                        self.assertIn('class="article-screen-pager" hidden', html)
                        images = re.findall(r'<img[^>]*class="article-screen-phone-image"[^>]*>', html)
                        self.assertEqual(
                            [re.search(r'data-screen="([^"]+)"', image).group(1) for image in images],
                            ["home", "lampada-journal", "lampada-question"],
                        )
                        for image, ref in zip(images, (refs[0], refs[1], refs[3])):
                            self.assertIn(f'alt="{ref.caption}"', image)
                            self.assertIn(f'data-app="{ref.screen.app}"', image)
                        buttons = re.findall(r'<button[^>]*class="article-screen-(?:previous|next|dot)"[^>]*>', html)
                        self.assertEqual(len(buttons), 5)
                        for button, label in zip(buttons, (previous, *(position.format(n=n) for n in range(1, 4)), following)):
                            self.assertIn('type="button"', button)
                            self.assertIn(f'aria-label="{label}"', button)
                        self.assertEqual(body.count('class="article-screen-inline"'), 4)

    def test_desktop_label_switches_only_with_decoded_screen(self) -> None:
        subprocess.run(["node", str(ROOT / "tests/article_screens.js")], check=True, capture_output=True, text=True)

    def test_unknown_or_misplaced_marker_fails_with_source(self) -> None:
        cases = (
            "## Heading\n<!-- screen: missing -->\n",
            "Paragraph\n<!-- screen: home -->\n",
            "## Heading\n\n<!-- screen: home -->\n",
            "## Heading\n<!-- screen: Home -->\n",
            "## Heading\n<!--  screen: home -->\n",
            "## Heading\n<!-- screen : home -->\n",
            "## Heading\n<!-- scren: home -->\n",
            "## Heading\n<!-- note -->\n",
            "## Heading\n> <!-- note -->\n",
            "## Heading\n> <!-- screen: home -->\n",
            "Paragraph\n> <!-- screen: home -->\n",
            "Paragraph\n<!-- scren: home -->\n",
            "Paragraph\n<!-- screeen: home -->\n",
        )
        for body in cases:
            with self.subTest(body=body), self.assertRaisesRegex(BuildError, "template-check/ru.md"):
                annotate_screens(body, SOURCE, "ru", self.screens)

    def test_existing_heading_class_and_source_line_are_preserved(self) -> None:
        body = "## Heading {.lead}\n<!-- screen: home -->\n\nText.\n"
        marked, _, refs = annotate_screens(body, SOURCE, "ru", self.screens, body_start_line=12)
        html = render_markdown(marked, refs, "Открыть: {caption}")
        self.assertIn('class="lead"', html)
        self.assertIn('data-screen="home"', html)
        self.assertIn('id="heading"', html)
        self.assertEqual(refs[0].line, 13)
        with self.assertRaises(BuildError) as failure:
            annotate_screens("## Heading\n<!--  screen: home -->\n", SOURCE, "ru", self.screens, body_start_line=12)
        self.assertIn(f"{SOURCE}:13:", str(failure.exception))

    def test_parser_reports_real_markdown_file_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ru.md"
            source.write_text("---\ntitle: Test\ndescription: Test\ndate: 2026-09-24\n---\n## Heading\n<!--  screen: home -->\n", encoding="utf-8")
            with self.assertRaises(BuildError) as failure:
                parse_article(source, "test", "ru", self.screens, self.checksums, {"screen_open": "Open: {caption}"}, ROOT / "dist/bible-garden")
            self.assertIn(f"{source}:7:", str(failure.exception))

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

    def test_unrelated_comment_outside_heading_is_allowed(self) -> None:
        body = "Paragraph\n\n<!-- editorial note -->\n"
        marked, clean, refs = annotate_screens(body, SOURCE, "ru", self.screens)
        self.assertEqual((marked, clean, refs), (body, body, ()))

    def test_marked_article_requires_open_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ru.md"
            source.write_text("---\ntitle: Test\ndescription: Test\ndate: 2026-09-24\n---\n## Heading\n<!-- screen: home -->\n", encoding="utf-8")
            with self.assertRaisesRegex(BuildError, "missing articles.screen_open translation"):
                parse_article(source, "test", "ru", self.screens, self.checksums, {}, ROOT / "dist/bible-garden")

    def test_asset_validation_rejects_missing_or_corrupt_webp(self) -> None:
        screen = self.screens["home"]
        checksum = self.checksums[screen.path("ru", "mobile")]
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with self.assertRaisesRegex(BuildError, "missing screenshot variant"):
                check_asset(screen, "ru", "mobile", output_dir, checksum)
            path = output_dir / screen.path("ru", "mobile")
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not a WebP")
            with self.assertRaisesRegex(BuildError, "invalid lossy WebP"):
                check_asset(screen, "ru", "mobile", output_dir, checksum)
            data = bytearray((ROOT / "static/bible-garden" / screen.path("ru", "mobile")).read_bytes())
            path.write_bytes(data)
            check_asset(screen, "ru", "mobile", output_dir, checksum)
            data[100] ^= 1
            path.write_bytes(data)
            with self.assertRaisesRegex(BuildError, "checksum differs"):
                check_asset(screen, "ru", "mobile", output_dir, checksum)

    def test_duplicate_catalog_keys_fail_with_line(self) -> None:
        cases = (
            "home:\n  kind: app\n  captions: {ru: Home}\nhome:\n  kind: app\n  captions: {ru: Again}\n",
            "home:\n  kind: app\n  captions:\n    ru: Home\n    ru: Again\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "screens.yaml"
            for text in cases:
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaisesRegex(BuildError, r"screens.yaml:\d+: duplicate key"):
                    load_catalog(path, ("ru",))

    def test_checksum_list_rejects_duplicate_and_missing_paths(self) -> None:
        screen = Screen("home", "app", {"ru": "Home"})
        lines = [f"{'0' * 64}  {screen.path('ru', variant)}\n" for variant in ("mobile", "phone", "zoom")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "screens.sha256"
            path.write_text("".join(lines + [lines[0]]), encoding="utf-8")
            with self.assertRaisesRegex(BuildError, "duplicate checksum"):
                load_checksums(path, {"home": screen}, ("ru",))
            path.write_text("".join(lines[:-1]), encoding="utf-8")
            with self.assertRaisesRegex(BuildError, "checksum paths differ"):
                load_checksums(path, {"home": screen}, ("ru",))

    def test_generated_phone_images_wait_for_desktop_activation(self) -> None:
        self.assertFalse((ROOT / "dist/bible-garden/ru/articles/template-check/index.html").exists())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview"
            build_all(preview=True, output_root=output)
            html = (output / "bible-garden/ru/articles/template-check/index.html").read_text(encoding="utf-8")
        images = re.findall(r'<img[^>]*class="article-screen-phone-image"[^>]*>', html)
        self.assertEqual(len(images), 2)
        for image in images:
            self.assertIn('data-src="/img/article-screens/phone/', image)
            self.assertNotIn(' src="', image)
        self.assertIn("<noscript><img", html)
        self.assertIn('class="article-screen-app-label" hidden', html)

if __name__ == "__main__":
    unittest.main()
