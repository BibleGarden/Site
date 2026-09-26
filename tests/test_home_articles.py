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

    def test_equal_dates_use_slug_order(self) -> None:
        original = self.builder.articles["how-to-start-reading-the-bible"]["en"]
        self.builder.articles = {
            slug: {"en": replace(original, slug=slug, date=date(2026, 9, 24))}
            for slug in ("bravo", "delta", "alpha", "charlie")
        }

        html = self.render("en")
        block = html.split('<section id="articles"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(
            re.findall(r'<a href="([^"]+)" class="feature-card', block),
            ["/articles/delta/", "/articles/charlie/", "/articles/bravo/"],
        )

    def test_base_footer_links_on_articles_and_pages(self) -> None:
        slug = "how-to-start-reading-the-bible"
        for lang in self.builder.site.languages:
            with self.subTest(page="article", lang=lang):
                self.builder.build_article(slug, lang)
                html = self.builder.output_path(lang, f"articles/{slug}/index.html").read_text(encoding="utf-8")
                footer = html.split("<footer", 1)[1].split("</footer>", 1)[0]
                self.assertIn(f'href="{self.builder.site.href(lang, "articles/")}"', footer)
                self.assertIn(self.builder.t(lang)["articles"]["section_title"], footer)

        self.builder.articles = {}
        for lang in self.builder.site.languages:
            with self.subTest(page="about", lang=lang):
                self.builder.build_page("about", lang)
                html = self.builder.output_path(lang, "about/index.html").read_text(encoding="utf-8")
                footer = html.split("<footer", 1)[1].split("</footer>", 1)[0]
                navigation = html.split("<nav", 1)[1].split("</nav>", 1)[0]
                article_href = f'href="{self.builder.site.href(lang, "articles/")}"'
                self.assertIn(article_href, footer)
                self.assertNotIn(article_href, navigation)

    def test_no_articles_hides_block(self) -> None:
        self.builder.articles = {}
        html = self.render("en")
        self.assertNotIn('<section id="articles"', html)
        self.assertIn('href="/articles/"', html)  # The footer remains available.


if __name__ == "__main__":
    unittest.main()
