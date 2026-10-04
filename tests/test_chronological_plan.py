"""Chronological calendar order, exact partition objective and localized HTML."""

from __future__ import annotations

import copy
import json
import random
import re
import tempfile
import unittest
from itertools import combinations
from pathlib import Path

from sitegen.chronological_plan import PLAN_PATH, compress_readings, load_plan, load_sequence, validate_plan
from sitegen.content import load_site, parse_article
from sitegen.errors import BuildError
from sitegen.reading_plan import MERGED_PAIRS, Chapter, annotate_plan_marker, display_chapter, format_range, render_plan
from tools.build_reading_plan import build_chronological_data, partition_uniform

ROOT = Path(__file__).resolve().parent.parent


class ChronologicalPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days, cls.chapters = load_plan()
        cls.stream = load_sequence(cls.chapters)
        cls.inventory = {(c.book, c.chapter): c for c in cls.chapters}
        cls.site = load_site(ROOT / "content/bible-garden", ROOT)

    def day_chapters(self, day):
        return [self.inventory[(r['book'], c)] for r in day['readings'] for c in range(r['first'], r['last'] + 1)]

    def test_committed_calendar_is_deterministic_and_preserves_all_chapters(self):
        self.assertEqual(build_chronological_data(), json.loads(PLAN_PATH.read_text()))
        flattened = [c for day in self.days for c in self.day_chapters(day)]
        self.assertEqual(flattened, self.stream)
        self.assertEqual(len(flattened), 1189)
        self.assertEqual(len({(c.book, c.chapter) for c in flattened}), 1189)
        day_by_chapter = {(c.book, c.chapter): day for day, value in enumerate(self.days) for c in self.day_chapters(value)}
        for book, chapter in MERGED_PAIRS:
            self.assertEqual(day_by_chapter[(book, chapter)], day_by_chapter[(book, chapter + 1)])
        self.assertAlmostEqual(sum(d['seconds'] for d in self.days), sum(c.tenths for c in self.chapters) / 10)

    def test_partition_matches_exhaustive_minimax_then_squared_objective(self):
        rng = random.Random(9)
        for count in range(3, 9):
            for _ in range(10):
                values = [rng.randrange(1, 40) for _ in range(count)]
                units = [Chapter(1, i + 1, {}, value) for i, value in enumerate(values)]
                days = rng.randrange(2, count)
                total = sum(values)

                def objective(chunks):
                    deviations = [abs(sum(chunk) * days - total) for chunk in chunks]
                    return max(deviations), sum(d * d for d in deviations)

                possibilities = []
                for cuts in combinations(range(1, count), days - 1):
                    boundaries = (0, *cuts, count)
                    possibilities.append(objective([values[a:b] for a, b in zip(boundaries, boundaries[1:])]))
                actual = partition_uniform(units, days)
                self.assertEqual(objective([[c.tenths for c in chunk] for chunk in actual]), min(possibilities))
        with self.assertRaises(ValueError):
            partition_uniform([], 1)

    def test_compression_keeps_every_jump_visible(self):
        chapters = [self.inventory[key] for key in ((19, 34), (19, 56), (9, 22), (19, 57), (19, 142), (19, 52), (19, 53))]
        self.assertEqual(compress_readings(chapters), [
            {'book': 19, 'first': 34, 'last': 34}, {'book': 19, 'first': 56, 'last': 56},
            {'book': 9, 'first': 22, 'last': 22}, {'book': 19, 'first': 57, 'last': 57},
            {'book': 19, 'first': 142, 'last': 142}, {'book': 19, 'first': 52, 'last': 53},
        ])

    def test_invalid_plan_data_fails_explicitly(self):
        mutations = (
            lambda d: d['days'].pop(),
            lambda d: d['days'][0].update(readings=[]),
            lambda d: d['days'][0].update(seconds=float('nan')),
            lambda d: d['days'][0]['readings'][0].update(book=True),
            lambda d: d['days'][0]['readings'][0].update(book=67),
            lambda d: d['days'][0]['readings'][0].update(first=0),
            lambda d: d['days'][0]['readings'][0].update(first=50, last=1),
            lambda d: d['days'][0]['readings'][0].update(last=51),
            lambda d: next(day for day in d['days'] if len(day['readings']) > 1)['readings'].reverse(),
        )
        for mutate in mutations:
            data = copy.deepcopy({'days': self.days})
            mutate(data)
            with self.subTest(mutation=mutate), self.assertRaises(BuildError):
                validate_plan(data, self.stream)

    def test_pair_cannot_cross_days_even_when_coverage_and_durations_match(self):
        for book, chapter in MERGED_PAIRS:
            data = copy.deepcopy({'days': self.days})
            index = next(i for i, day in enumerate(data['days']) if (book, chapter) in {(c.book, c.chapter) for c in self.day_chapters(day)})
            current = self.day_chapters(data['days'][index])
            following = self.day_chapters(data['days'][index + 1])
            cut = next(i + 1 for i, c in enumerate(current) if (c.book, c.chapter) == (book, chapter))
            for target, chapters in ((index, current[:cut]), (index + 1, current[cut:] + following)):
                data['days'][target] = {'readings': compress_readings(chapters), 'seconds': sum(c.tenths for c in chapters) / 10}
            with self.subTest(pair=(book, chapter)), self.assertRaisesRegex(BuildError, 'splits a merged'):
                validate_plan(data, self.stream)

    def test_single_calendar_renders_all_localized_readings_without_javascript(self):
        for lang in ('en', 'ru', 'uk'):
            strings = self.site.i18n[lang]['articles']['reading_plan']
            rendered = render_plan([], [], self.chapters, lang, strings, chronological=self.days)
            self.assertEqual(len(re.findall(r'<tr data-day="\d+">', rendered)), 365)
            self.assertEqual(rendered.count('<details class="reading-plan-month"'), 12)
            self.assertEqual(rendered.count('<details class="reading-plan-month" open>'), 1)
            self.assertNotIn('reading-plan-switcher', rendered)
            self.assertIn('data-plan-kind="chronological"', rendered)
            self.assertIn('data-day="365"', rendered)
            self.assertEqual(rendered.count('class="reading-plan-checkbox"'), 365)
            self.assertIn(' · ', rendered)
        names = {c.book: c.names['ru'] for c in self.chapters}
        value = {'start': {'book': 19, 'chapter': 51}, 'end': {'book': 19, 'chapter': 51}}
        self.assertEqual(format_range(value, names, 'ru'), 'Псалтирь 50')
        self.assertEqual(display_chapter('ru', 19, 50), (49, 49))
        self.assertEqual(display_chapter('uk', 19, 51), (51, 51))
        self.assertEqual(display_chapter('uk', 39, 4), (3, 3))
        uk_names = {c.book: c.names['uk'] for c in self.chapters}
        malachi = {'start': {'book': 39, 'chapter': 3}, 'end': {'book': 39, 'chapter': 4}}
        self.assertEqual(format_range(malachi, uk_names, 'uk'), f"{uk_names[39]} 3")

    def test_marker_renders_article_and_rejects_duplicates_and_other_sites(self):
        marker = '<!-- plan: chronological-bible-reading-plan -->'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'ru.md'
            source.write_text('---\ntitle: Test\ndescription: Test\ndate: 2026-10-04\n---\n' + marker + '\n')
            article = parse_article(source, 'test', 'ru', {}, {}, self.site.i18n['ru']['articles'], ROOT / 'dist/bible-garden')
            self.assertTrue(article.has_plan)
            self.assertTrue(article.has_chronological_plan)
            self.assertNotIn('placeholder', article.body_html)
            for body, site in ((marker + '\n' + marker, 'bible-garden'), (marker, 'lampada')):
                with self.assertRaises(BuildError):
                    annotate_plan_marker(body, source, site)
