"""Lampada landing navigation and recent published articles."""

from __future__ import annotations

import re
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from markupsafe import escape

from sitegen.build import SiteBuilder

ROOT = Path(__file__).resolve().parent.parent


class LampadaHomeArticlesTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.builder = SiteBuilder(ROOT / "content/lampada", Path(directory.name) / "lampada", preview=True)
        self.fixtures = self.builder.articles["template-check"]

    def render(self, lang: str) -> str:
        self.builder.build_landing(lang)
        return self.builder.output_path(lang, "index.html").read_text(encoding="utf-8")

    def test_header_and_footer_with_only_drafts(self) -> None:
        for lang in self.builder.site.languages:
            with self.subTest(lang=lang):
                html = self.render(lang)
                strings = self.builder.t(lang)["landing"]
                nav = html.split('<nav class="site-nav"', 1)[1].split("</nav>", 1)[0]
                self.assertEqual(re.findall(r'<a href="([^"]+)">([^<]+)</a>', nav), [
                    (self.builder.site.href(lang, "articles/"), strings["nav"]["articles"]),
                    ("#purpose", strings["nav"]["about"]),
                ])
                footer = html.split("<footer", 1)[1].split("</footer>", 1)[0]
                suffix = "" if lang == self.builder.site.default_language else f"?lang={lang}"
                self.assertEqual(re.findall(r'<a href="([^"]+)">([^<]+)</a>', footer), [
                    (self.builder.site.config["privacy_url"] + suffix, strings["nav"]["privacy"]),
                    (self.builder.site.config["support_url"] + suffix, strings["nav"]["support"]),
                    (self.builder.site.config["bible_garden_url"], strings["footer"]["bible_garden"]),
                ])
                self.assertNotIn('id="articles"', html)

    def test_latest_three_published_articles_in_each_language(self) -> None:
        self.builder.articles = {
            slug: {
                lang: replace(original, slug=slug, title=f"{lang}: {slug} & prayer",
                              description=f"{lang}: <reflection>", date=date(2026, 10, day), draft=draft)
                for lang, original in self.fixtures.items()
            }
            for slug, day, draft in (
                ("oldest", 1, False), ("second", 2, False), ("third", 3, False),
                ("latest", 4, False), ("draft", 5, True),
            )
        }
        for preview in (False, True):
            self.builder.preview = preview
            for lang in self.builder.site.languages:
                with self.subTest(preview=preview, lang=lang):
                    html = self.render(lang)
                    block = html.split('id="articles"', 1)[1].split("</section>", 1)[0]
                    self.assertEqual(re.findall(r'<a href="([^"]+)">', block), [
                        self.builder.site.href(lang, f"articles/{slug}/") for slug in ("latest", "third", "second")
                    ])
                    self.assertIn(str(escape(f"{lang}: latest & prayer")), block)
                    self.assertIn(str(escape(f"{lang}: <reflection>")), block)
                    self.assertIn('<time datetime="2026-10-04">2026-10-04</time>', block)
                    self.assertIn(f'>{self.builder.t(lang)["landing"]["articles"]["all"]}</a>', block)
                    self.assertIn(f'href="{self.builder.site.href(lang, "articles/")}"', block)
                    self.assertNotIn("oldest", block)
                    self.assertNotIn("draft", block)

    def test_block_hidden_for_language_without_publications(self) -> None:
        self.builder.articles = {"published": {"en": replace(self.fixtures["en"], slug="published", draft=False)}}
        self.assertIn('id="articles"', self.render("en"))
        for lang in ("ru", "uk"):
            self.assertNotIn('id="articles"', self.render(lang))
        self.builder.articles = {}
        self.assertNotIn('id="articles"', self.render("en"))


if __name__ == "__main__":
    unittest.main()
