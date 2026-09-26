"""Recent published articles on the Bible Garden landing page."""

from __future__ import annotations

import re
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from sitegen.build import SiteBuilder

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content/bible-garden"


class HomeArticlesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.builder = SiteBuilder(CONTENT, Path(self.directory.name) / "bible-garden", preview=False)

    def render(self, lang: str) -> str:
        self.builder.build_landing(lang)
        return self.builder.output_path(lang, "index.html").read_text(encoding="utf-8")

    def test_latest_three_published_articles_exclude_drafts(self) -> None:
        original = self.builder.articles["how-to-start-reading-the-bible"]["en"]
        self.builder.articles = {
            slug: {"en": replace(original, slug=slug, title=slug, date=date(2026, 9, day), draft=draft)}
            for slug, day, draft in (
                ("oldest", 1, False),
                ("second", 2, False),
                ("third", 3, False),
                ("latest", 4, False),
                ("draft", 5, True),
            )
        }

        html = self.render("en")
        block = html.split('<section id="articles"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(
            re.findall(r'<a href="([^"]+)" class="feature-card', block),
            ["/articles/latest/", "/articles/third/", "/articles/second/"],
        )
        self.assertNotIn("oldest", block)
        self.assertNotIn("draft", block)
        self.assertIn('<a href="/articles/"', block)

    def test_each_language_uses_its_own_published_article(self) -> None:
        for lang, prefix in (("en", "/"), ("ru", "/ru/"), ("uk", "/uk/")):
            with self.subTest(lang=lang):
                article = self.builder.articles["how-to-start-reading-the-bible"][lang]
                html = self.render(lang)
                block = html.split('<section id="articles"', 1)[1].split("</section>", 1)[0]
                self.assertIn(article.title, block)
                self.assertIn(article.description, block)
                self.assertIn(f'href="{prefix}{article.path}"', block)
                self.assertIn(f'href="{prefix}articles/"', block)
                self.assertNotIn("template-check", block)

    def test_no_articles_hides_block(self) -> None:
        self.builder.articles = {}
        html = self.render("en")
        self.assertNotIn('<section id="articles"', html)
        self.assertIn('href="/articles/"', html)  # The footer remains available.


if __name__ == "__main__":
    unittest.main()
