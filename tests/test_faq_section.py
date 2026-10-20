"""The '{#faq}' section is wrapped in its own <section> without changing its content."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
import unittest
from xml.etree import ElementTree as ET

from sitegen.build import Page, SiteBuilder
from sitegen.content import Article, extract_faq, render_markdown

BODY = """Intro[^note].

## Questions {#faq}

### First?

Answer one.

### Second?

Answer two.

## After

Text.

[^note]: A footnote.
"""


def children(html: str) -> list[ET.Element]:
    return list(ET.fromstring(f"<root>{html}</root>"))


class FaqSectionTest(unittest.TestCase):
    def test_section_spans_faq_heading_to_next_h2(self) -> None:
        nodes = children(render_markdown(BODY, lang="en"))
        self.assertEqual([node.tag for node in nodes], ["p", "section", "h2", "p", "div"])
        section = nodes[1]
        self.assertEqual(section.attrib, {"class": "article-faq", "aria-labelledby": "faq"})
        self.assertEqual([(node.tag, node.get("id")) for node in section][:2], [("h2", "faq"), ("h3", "first")])
        self.assertEqual([node.tag for node in section], ["h2", "h3", "p", "h3", "p"])

    def test_footnotes_stay_outside_a_trailing_faq(self) -> None:
        body = BODY.replace("## After\n\nText.\n\n", "")
        nodes = children(render_markdown(body, lang="en"))
        self.assertEqual([node.tag for node in nodes], ["p", "section", "div"])
        self.assertEqual(nodes[2].get("class"), "footnote")

    def test_body_without_faq_is_unchanged(self) -> None:
        self.assertNotIn("<section", render_markdown("## Heading\n\nText.\n", lang="en"))

    def test_json_ld_answer_omits_markdown_footnote_marker(self) -> None:
        faq = extract_faq(
            "## Questions {#faq}\n\n### Question?\n\nAnswer with *emphasis*[^source].\n",
            source=__file__,
            lang="en",
        )
        article = Article(
            slug="fixture", lang="en", title="Fixture", description="Test", date=date(2026, 10, 20),
            updated=None, draft=False, image=None, body_html="", faq=faq, screens=(),
        )
        builder = SiteBuilder.__new__(SiteBuilder)
        builder.site = SimpleNamespace(
            base_url="https://example.test",
            name="Example",
            config={"logo": "/logo.png"},
            author=SimpleNamespace(json_ld=lambda site, lang: {"@type": "Organization", "name": "Example"}),
            url=lambda lang, path="": f"https://example.test/{path}",
        )
        builder.t = lambda lang: {"articles": {"breadcrumb_home": "Home", "section_title": "Articles"}}
        schema = builder.article_json_ld(
            article,
            Page("en", "en", "Fixture", "Test", {"en": "https://example.test/articles/fixture/"}, "https://example.test/logo.png"),
        )
        answer = schema[-1]["mainEntity"][0]["acceptedAnswer"]["text"]
        self.assertEqual(answer, "Answer with emphasis.")
        self.assertNotIn("[^", answer)


if __name__ == "__main__":
    unittest.main()
