"""Bible in a year data, article marker and localized calendar."""

from __future__ import annotations

import re
import tempfile
import unittest
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

from sitegen.build import SiteBuilder
from sitegen.content import load_site, parse_article
from sitegen.errors import BuildError
from sitegen.reading_plan import (
    DISPLAY_RULES, MERGED_PAIRS, Chapter, annotate_plan_marker, display_chapter,
    format_range, load_chapters, load_plan, load_plans, load_sequential_plan,
    reading_units, render_plan, streams, validate_plan, validate_sequential_plan,
)
from tools.build_reading_plan import build_data, build_sequential_data, partition

ROOT = Path(__file__).resolve().parent.parent


class ReadingPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.days, cls.sequential_days, cls.chapters = load_plans()

    def test_generator_covers_each_stream_once_in_order(self) -> None:
        a, b = streams(self.chapters)
        self.assertEqual(build_data(), {"days": self.days})
        self.assertEqual(len(a) + len(b), 1189)
        self.assertEqual(len(self.days), 365)
        self.assertEqual([item.book for item in b[:3]], [40, 40, 40])
        self.assertEqual(next(item.names["en"] for item in b if item.book == 45), "Romans")
        self.assertEqual(next(item.names["en"] for item in b if item.book == 59), "James")
        self.assertEqual(next(item.names["ru"] for item in a if item.book == 22), "Песнь песней")
        self.assertEqual([item.book for item in b[-3:]], [19, 19, 19])
        for stream in (a, b):
            units = reading_units(stream)
            self.assertEqual([chapter for unit in units for chapter in unit.chapters], stream)
        for day in self.days:
            for key in ("a", "b"):
                self.assertNotIn((day[key]["end"]["book"], day[key]["end"]["chapter"]), MERGED_PAIRS)

    def test_sequential_plan_covers_canonical_order_once(self) -> None:
        self.assertEqual(build_sequential_data(), {"days": self.sequential_days})
        self.assertEqual(len(self.sequential_days), 365)
        self.assertEqual(self.sequential_days[0]["reading"]["start"], {"book": 1, "chapter": 1})
        self.assertEqual(self.sequential_days[-1]["reading"]["end"], {"book": 66, "chapter": 22})
        self.assertTrue(any(day["reading"]["start"]["book"] != day["reading"]["end"]["book"] for day in self.sequential_days))
        self.assertAlmostEqual(sum(day["seconds"] for day in self.sequential_days), sum(chapter.tenths for chapter in self.chapters) / 10)
        for day in self.sequential_days:
            self.assertNotIn((day["reading"]["end"]["book"], day["reading"]["end"]["chapter"]), MERGED_PAIRS)

    def test_partition_uses_day_total_targets_and_squared_error(self) -> None:
        values = [10, 12, 8, 8, 10]
        offsets = [5, 20, 0]
        chapters = [Chapter(1, number, {"en": "Test"}, value) for number, value in enumerate(values, 1)]
        chunks = partition(chapters, days=3, offsets=offsets, target_total=sum(values) + sum(offsets))

        def score(sums: list[int]) -> tuple[int, int]:
            deviations = [abs((value + offsets[index]) * 3 - sum(values) - sum(offsets)) for index, value in enumerate(sums)]
            return max(deviations), sum(value * value for value in deviations)

        possible = []
        for first, second in combinations(range(1, len(values)), 2):
            possible.append(score([sum(values[:first]), sum(values[first:second]), sum(values[second:])]))
        self.assertEqual(score([sum(item.tenths for item in chunk) for chunk in chunks]), min(possible))

    def test_committed_plan_validates_and_rejects_corruption(self) -> None:
        validate_plan({"days": self.days}, self.chapters)
        changed = [dict(day) for day in self.days]
        changed[0]["seconds"] = 0
        with self.assertRaisesRegex(BuildError, "incorrect total seconds"):
            validate_plan({"days": changed}, self.chapters)
        changed[0] = dict(self.days[0], a=self.days[1]["a"])
        with self.assertRaisesRegex(BuildError, "does not start at the next chapter"):
            validate_plan({"days": changed}, self.chapters)
        for book, chapter in MERGED_PAIRS:
            key = "a" if book == 39 else "b"
            changed = [dict(day) for day in self.days]
            changed[0] = dict(self.days[0], **{key: dict(self.days[0][key], end={"book": book, "chapter": chapter})})
            with self.subTest(book=book, chapter=chapter), self.assertRaisesRegex(BuildError, "boundary splits a merged chapter unit"):
                validate_plan({"days": changed}, self.chapters)

        validate_sequential_plan({"days": self.sequential_days}, self.chapters)
        changed = [dict(day) for day in self.sequential_days]
        changed[0]["seconds"] = 0
        with self.assertRaisesRegex(BuildError, "incorrect total seconds"):
            validate_sequential_plan({"days": changed}, self.chapters)
        changed = [dict(day) for day in self.sequential_days]
        changed[0] = dict(self.sequential_days[0], reading=dict(self.sequential_days[0]["reading"], end={"book": 19, "chapter": 9}))
        with self.assertRaisesRegex(BuildError, "boundary splits a merged chapter unit"):
            validate_sequential_plan({"days": changed}, self.chapters)

    def test_localized_chapter_numbering(self) -> None:
        names = {19: "Псалмы", 39: "Малахії"}

        def span(book: int, first: int, last: int) -> dict:
            return {"start": {"book": book, "chapter": first}, "end": {"book": book, "chapter": last}}

        cases = (
            ("ru", 19, 1, 8, "Псалмы 1–8"),
            ("ru", 19, 9, 10, "Псалмы 9"),
            ("ru", 19, 11, 113, "Псалмы 10–112"),
            ("ru", 19, 114, 115, "Псалмы 113"),
            ("ru", 19, 116, 116, "Псалмы 114–115"),
            ("ru", 19, 117, 146, "Псалмы 116–145"),
            ("ru", 19, 147, 147, "Псалмы 146–147"),
            ("ru", 19, 148, 150, "Псалмы 148–150"),
            ("uk", 39, 1, 4, "Малахії 1–3"),
            ("uk", 39, 3, 4, "Малахії 3"),
            ("uk", 19, 9, 10, "Псалмы 9–10"),
            ("en", 19, 116, 116, "Псалмы 116"),
        )
        for lang, book, first, last, expected in cases:
            with self.subTest(lang=lang, book=book, first=first, last=last):
                self.assertEqual(format_range(span(book, first, last), names, lang), expected)
        with patch.dict(DISPLAY_RULES["uk"], {39: ((1, 3, 1, 3), (4, 4, 4, 3))}):
            with self.assertRaisesRegex(BuildError, "invalid displayed chapter range"):
                display_chapter("uk", 39, 4)

    def test_marker_errors_include_article_line(self) -> None:
        source = Path("content/bible-garden/articles/example/ru.md")
        for line in (
            "<!-- plan: unknown -->",
            "<!--  plan: bible-in-a-year -->",
            "<!-- plan : bible-in-a-year -->",
            "<!-- plan: Bible-in-a-year -->",
            "> <!-- plan: bible-in-a-year -->",
        ):
            with self.subTest(line=line), self.assertRaisesRegex(BuildError, r"ru.md:9:"):
                annotate_plan_marker(f"Text\n{line}\n", source, "bible-garden", 8)
        with self.assertRaisesRegex(BuildError, "duplicate reading plan marker"):
            annotate_plan_marker("<!-- plan: bible-in-a-year -->\n<!-- plan: bible-in-a-year -->", source, "bible-garden")
        with self.assertRaisesRegex(BuildError, "unknown plan"):
            annotate_plan_marker("<!-- plan: bible-in-a-year -->", source, "lampada")
        body, found = annotate_plan_marker("```html\n<!-- plan: bible-in-a-year -->\n```\n", source, "bible-garden")
        self.assertFalse(found)
        self.assertIn("<!-- plan: bible-in-a-year -->", body)

    def test_article_renders_both_localized_calendars(self) -> None:
        strings = {
            "en": {"choose_plan": "Reading order", "parallel": "Parallel", "sequential": "Straight through", "start_date": "Start date", "print": "Print", "day": "Day", "date": "Date", "reading": "Reading", "days": "Days {first}–{last}", "caption_days": "Reading plan: days {first}–{last}", "caption_month": "Reading plan: {month}, days {first}–{last}", "done": "Done"},
            "ru": {"choose_plan": "Порядок чтения", "parallel": "Параллельно", "sequential": "Подряд", "start_date": "Дата начала", "print": "Распечатать", "day": "День", "date": "Дата", "reading": "Чтение", "days": "Дни {first}–{last}", "caption_days": "План чтения: дни {first}–{last}", "caption_month": "План чтения: {month}, дни {first}–{last}", "done": "Отметка"},
            "uk": {"choose_plan": "Порядок читання", "parallel": "Паралельно", "sequential": "Підряд", "start_date": "Дата початку", "print": "Роздрукувати", "day": "День", "date": "Дата", "reading": "Читання", "days": "Дні {first}–{last}", "caption_days": "План читання: дні {first}–{last}", "caption_month": "План читання: {month}, дні {first}–{last}", "done": "Позначка"},
        }
        for lang, first_name in (("en", "Genesis"), ("ru", "Бытие"), ("uk", "Буття")):
            with self.subTest(lang=lang):
                with tempfile.TemporaryDirectory() as directory:
                    source = Path(directory) / f"{lang}.md"
                    source.write_text("---\ntitle: Test\ndescription: Test\ndate: 2026-09-27\n---\n## Calendar\n<!-- plan: bible-in-a-year -->\n", encoding="utf-8")
                    article = parse_article(source, "test", lang, {}, {}, {"reading_plan": strings[lang]}, ROOT / "dist/bible-garden")
                html = article.body_html
                self.assertTrue(article.has_plan)
                self.assertEqual(len(re.findall(r'<tr data-day="\d+">', html)), 730)
                self.assertEqual(html.count('<details class="reading-plan-month"'), 24)
                self.assertEqual(html.count('<details class="reading-plan-month" open>'), 2)
                self.assertEqual(html.count('<caption class="sr-only">'), 24)
                self.assertIn('<fieldset class="reading-plan-switcher" hidden>', html)
                self.assertIn('data-plan-kind="parallel"', html)
                self.assertIn('data-plan-kind="sequential"', html)
                self.assertIn(f'>{strings[lang]["parallel"]}</h3>', html)
                self.assertIn(f'>{strings[lang]["sequential"]}</h3>', html)
                self.assertIn(strings[lang]["days"].format(first=1, last=31), html)
                self.assertIn(strings[lang]["days"].format(first=32, last=62), html)
                self.assertIn(strings[lang]["days"].format(first=342, last=365), html)
                self.assertIn(strings[lang]["caption_days"].format(first=94, last=124), html)
                self.assertIn(f'<span class="sr-only">{strings[lang]["done"]}</span>', html)
                self.assertIn(f"{first_name} 1", html)
                self.assertIn('data-day="365"', html)
                self.assertIn(strings[lang]["start_date"], html)
                self.assertIn('class="reading-plan-date"></td>', html)
                self.assertNotIn("<!-- plan:", html)

    def test_article_page_marks_plan_for_print_without_has_selector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            builder = SiteBuilder(ROOT / "content/bible-garden", Path(directory) / "bible-garden", preview=True)
            slug = "how-to-start-reading-the-bible"
            article = builder.articles[slug]["en"]
            builder.articles[slug]["en"] = replace(article, has_plan=True)
            builder.build_article(slug, "en")
            page = builder.output_path("en", f"articles/{slug}/index.html").read_text(encoding="utf-8")
        self.assertIn('antialiased has-reading-plan">', page)
        css = (ROOT / "static/bible-garden/css/article.css").read_text(encoding="utf-8")
        self.assertNotIn(":has(", css)
        self.assertNotIn("break-before: page", css)
        self.assertIn(".reading-plan-month tr { break-inside: avoid", css)

    def test_group_labels_reject_extra_placeholders(self) -> None:
        site = load_site(ROOT / "content/bible-garden", ROOT)
        strings = dict(site.i18n["en"]["articles"]["reading_plan"])
        strings["days"] += " {month}"
        with self.assertRaisesRegex(BuildError, "needs exactly first, last"):
            render_plan(self.days, self.sequential_days, self.chapters, "en", strings)

    def test_missing_source_or_plan_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.tsv"
            with self.assertRaisesRegex(BuildError, "missing chapter source"):
                load_chapters(missing)
            with self.assertRaisesRegex(BuildError, "missing reading plan"):
                load_plan(Path(directory) / "missing.json")
            with self.assertRaisesRegex(BuildError, "missing reading plan"):
                load_sequential_plan(Path(directory) / "missing-sequential.json")
            invalid = Path(directory) / "invalid.json"
            invalid.write_text('{"days": [], "days": []}', encoding="utf-8")
            with self.assertRaisesRegex(BuildError, "duplicate JSON key"):
                load_plan(invalid)


if __name__ == "__main__":
    unittest.main()
