"""Chapter inventory, localized order and strict article marker integration."""

import re
import tempfile
import unittest
from pathlib import Path

from sitegen.bible_checklist import MARKER, PLACEHOLDER, annotate_checklist_marker, checklist_books, render_checklist
from sitegen.content import parse_article
from sitegen.errors import BuildError

ROOT = Path(__file__).resolve().parent.parent


class BibleChecklistTest(unittest.TestCase):
    def test_localized_inventory_and_order(self):
        for lang, total in (("ru", 1189), ("en", 1189), ("uk", 1188)):
            with self.subTest(lang=lang):
                books = checklist_books(lang)
                self.assertEqual(len(books), 66)
                self.assertEqual(len({book for book, _, _ in books}), 66)
                self.assertEqual(sum(len(chapters) for _, _, chapters in books), total)
                for _, _, chapters in books:
                    self.assertEqual(chapters, list(range(1, len(chapters) + 1)))
                inventory = {book: chapters for book, _, chapters in books}
                self.assertEqual(len(inventory[19]), 150)
                self.assertEqual(len(inventory[39]), 3 if lang == "uk" else 4)
                self.assertEqual(len(inventory[14]), 36)
                self.assertEqual(len(inventory[17]), 10)
                self.assertEqual(len(inventory[27]), 12)
                self.assertEqual(books[0][1], {"ru": "Бытие", "en": "Genesis", "uk": "Буття"}[lang])
                expected = list(range(1, 67))
                if lang == "ru":
                    expected = list(range(1, 45)) + list(range(59, 66)) + list(range(45, 59)) + [66]
                self.assertEqual([book for book, _, _ in books], expected)
                rendered = render_checklist(lang)
                self.assertEqual(rendered.count('type="checkbox"'), total)
                self.assertEqual(rendered.count('class="checklist-sheet"'), 2)
                self.assertIn(str(total), rendered)
                self.assertNotIn('<table', rendered)
                self.assertEqual(len(re.findall(r'aria-label="[^"]+ \d+"', rendered)), total)
        with self.assertRaises(BuildError):
            render_checklist("de")

    def test_marker_validation(self):
        source = Path("ru.md")
        self.assertEqual(annotate_checklist_marker(MARKER + "\n", source, "bible-garden"), (PLACEHOLDER + "\n", True))
        for invalid in ("<!-- checklist: unknown -->", "<!-- checklist:bible-chapters -->", "> " + MARKER,
                        MARKER + " trailing", "<!-- CHECKLIST: bible-chapters -->", "<!-- cheklist: bible-chapters -->"):
            with self.subTest(marker=invalid), self.assertRaisesRegex(BuildError, "ru.md:9:"):
                annotate_checklist_marker("Text\n" + invalid, source, "bible-garden", 8)
        with self.assertRaisesRegex(BuildError, "duplicate"):
            annotate_checklist_marker(MARKER + "\n" + MARKER, source, "bible-garden")
        with self.assertRaisesRegex(BuildError, "only supported"):
            annotate_checklist_marker(MARKER, source, "lampada")
        for fence in ("```", "~~~"):
            body = fence + "html\n" + MARKER + "\n" + fence
            self.assertEqual(annotate_checklist_marker(body, source, "bible-garden"), (body, False))

    def test_article_integration(self):
        for lang in ("ru", "en", "uk"):
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / f"{lang}.md"
                source.write_text("---\ntitle: Test\ndescription: Test\ndate: 2026-10-04\n---\nBefore\n\n" + MARKER + "\n\nAfter\n")
                article = parse_article(source, "test", lang, {}, {}, {}, ROOT / "dist/bible-garden")
            self.assertTrue(article.has_checklist)
            self.assertFalse(article.has_plan)
            self.assertIn('class="bible-checklist"', article.body_html)
            self.assertNotIn(PLACEHOLDER, article.body_html)
            self.assertIn("Before", article.body_html)
            self.assertIn("After", article.body_html)

    def test_print_css_and_script_are_scoped(self):
        css = (ROOT / "static/bible-garden/css/article.css").read_text()
        for rule in ("@page bible-checklist", "size: A4 portrait", "break-after: page", "columns: 3",
                     ".has-bible-checklist .article-body > :not(.bible-checklist)", "appearance: none"):
            self.assertIn(rule, css)
        template = (ROOT / "templates/bible-garden/article.html").read_text()
        self.assertIn("article.has_checklist", template)
        self.assertIn("/js/bible-checklist.js", template)
        script = (ROOT / "static/bible-garden/js/bible-checklist.js").read_text()
        self.assertIn("window.print()", script)
        self.assertNotIn("localStorage", script)
