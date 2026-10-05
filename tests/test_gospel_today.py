"""Calendar regressions, source accuracy, offline regeneration and article integration."""
from __future__ import annotations

import copy
import json
import shutil
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sitegen.content import load_site, parse_article
from sitegen.errors import BuildError
from sitegen.gospel_today import MARKER, PLACEHOLDER, annotate_marker, render_component
from sitegen.lectionary_data import (ROOT, SOURCE, BUNDLE_DIR, load_bundle, validate_passages, validate_schedule, daily_files, validate_daily, referenced_passages)
from tools.build_gospel_today import generate, extract_passage, display_ranges, export_local, normalize_known_joins, UBH_MATTHEW_23_14


class GospelAssetsTest(unittest.TestCase):
    def test_offline_regeneration_and_bundle(self):
        with patch('tools.build_gospel_today.local_query', side_effect=AssertionError('DB forbidden')):
            generated = generate()
        self.assertEqual(set(generated), {str(p.relative_to(BUNDLE_DIR)) for p in BUNDLE_DIR.rglob('*.json')})
        for name, value in generated.items(): self.assertEqual((BUNDLE_DIR / name).read_bytes(), value)
        manifest, assets = load_bundle()
        self.assertEqual((manifest['start_year'], manifest['end_year']), (2026, 2030))
        self.assertTrue(assets['uk/2027.json']['days']['2027-01-12']['uncertain'])

    def test_daily_files_are_complete_minimal_and_match_source(self):
        manifest, assets = load_bundle()
        files = daily_files(manifest, assets)
        self.assertEqual(len(files), 3652)
        expected = {f'{lang}/{year}/{date[5:]}.json' for lang in ('ru', 'uk') for year in range(2026, 2031) for date in assets[f'{lang}/{year}.json']['days']}
        self.assertEqual(set(files), expected)
        for filename, payload in files.items():
            lang, year, name = filename.split('/')
            date = year + '-' + name.removesuffix('.json')
            data = json.loads(payload)
            validate_daily(data, lang, date)
            self.assertEqual(set(data['passages']), referenced_passages({date: data['day']}))
            self.assertEqual(data['day'], assets[f'{lang}/{year}.json']['days'][date])
            for pid, passage in data['passages'].items():
                self.assertEqual(passage, assets[f'{lang}/texts.json']['passages'][pid])
            self.assertEqual((ROOT / 'dist/bible-garden/data/gospel-today' / filename).read_bytes(), payload)
        january = json.loads(files['ru/2027/01-01.json'])
        for mutation in ('missing_day', 'missing_text', 'extra_text', 'wrong_date', 'invalid_date'):
            changed = copy.deepcopy(january)
            if mutation == 'missing_day': del changed['day']
            if mutation == 'missing_text': changed['passages'].pop(next(iter(changed['passages'])))
            if mutation == 'extra_text':
                pid = next(p for p in assets['ru/texts.json']['passages'] if p not in changed['passages'])
                changed['passages'][pid] = assets['ru/texts.json']['passages'][pid]
            if mutation == 'wrong_date': changed['date'] = '2026-01-01'
            if mutation == 'invalid_date': changed['date'] = '2027-02-29'
            date = changed['date'] if mutation == 'invalid_date' else '2027-01-01'
            with self.subTest(mutation=mutation), self.assertRaises(BuildError): validate_daily(changed, 'ru', date)
        self.assertIn('ru/2028/02-29.json', files)
        self.assertNotIn('ru/2027/02-29.json', files)

    def test_passage_missing_text_and_schedule_missing_day_fail(self):
        _, assets = load_bundle()
        texts = copy.deepcopy(assets['ru/texts.json'])
        passage = next(iter(texts['passages'].values()))
        passage['verses'][0]['text'] = ''
        with self.assertRaises(BuildError): validate_passages(texts, 'ru')
        schedule = copy.deepcopy(assets['uk/2026.json']); del schedule['days']['2026-01-01']
        with self.assertRaises(BuildError): validate_schedule(schedule, 'uk', 2026, assets['uk/texts.json']['passages'])
        schedule = copy.deepcopy(assets['uk/2026.json'])
        schedule['days']['2026-01-01']['uncertain'] = False
        schedule['days']['2026-01-01']['confirmed_by'] = []
        with self.assertRaises(BuildError): validate_schedule(schedule, 'uk', 2026, assets['uk/texts.json']['passages'])

    def test_explicit_versification_joined_verses_and_missing_data(self):
        ref = {'book': 45, 'ranges': [[14, 19, 14, 26]]}
        self.assertEqual(display_ranges(ref, 'ubh'), [[14, 19, 14, 23], [16, 25, 16, 27]])
        ref = {'book': 40, 'ranges': [[1, 1, 1, 3]]}
        verses = {'40:1:1': {'last': 2, 'text': 'one and two'}, '40:1:3': {'last': 3, 'text': 'three'}}
        passage = extract_passage(ref, 'syn', verses, {'40': {'ru_abbr': 'Мф', 'ru': 'Матфей'}}, 'ru')
        self.assertEqual(len(passage['verses']), 2)
        del verses['40:1:3']
        with self.assertRaisesRegex(BuildError, 'missing verses'): extract_passage(ref, 'syn', verses, {'40': {'ru_abbr': 'Мф', 'ru': 'Матфей'}}, 'ru')

    def test_marker_and_draft_fixture(self):
        body, found = annotate_marker(MARKER, Path('x.md'), 'bible-garden', 'ru')
        self.assertTrue(found); self.assertIn(PLACEHOLDER, body)
        for value in (' '+MARKER, MARKER+'\n'+MARKER, '<!-- gospel_today -->', '<!-- gospel-today-->', '> '+MARKER):
            with self.subTest(value=value), self.assertRaises(BuildError): annotate_marker(value, Path('x.md'), 'bible-garden', 'ru')
        for lang, site in [('en', 'bible-garden'), ('ru', 'lampada')]:
            with self.assertRaises(BuildError): annotate_marker(MARKER, Path('x.md'), site, lang)
        self.assertFalse(annotate_marker('```\n'+MARKER+'\n```', Path('x.md'), 'bible-garden', 'ru')[1])
        site = load_site(ROOT / 'content/bible-garden', ROOT)
        for lang in ('ru', 'uk'):
            article = parse_article(ROOT / f'tests/fixtures/gospel-today/{lang}.md', 'gospel-today-fixture', lang, {}, {}, site.i18n[lang]['articles'], ROOT / '.preview/bible-garden', app_store_url=site.article_app_store_url(lang), gospel_audio=site.config["gospel_audio"])
            self.assertTrue(article.draft); self.assertTrue(article.has_gospel_today)
            self.assertIn('data-gospel-today', article.body_html)
            self.assertIn('data-umami-event="app-store-click"', article.body_html)
            self.assertEqual('radiovera.ru' in article.body_html, lang == 'ru')
            with self.assertRaises(BuildError): render_component(lang, {}, site.article_app_store_url(lang))
        self.assertFalse(any(MARKER in p.read_text() for p in (ROOT / 'content/bible-garden/articles').rglob('*.md')))

    def test_verified_khomenko_join_is_explicit_and_guarded(self):
        rows = {'syn': {}, 'ubh': {
            '40:23:13': {'last': 13, 'text': 'preceding verse'},
            '40:23:14': {'last': 14, 'text': UBH_MATTHEW_23_14},
            '40:23:15': {'last': 15, 'text': ''},
            '40:23:16': {'last': 16, 'text': 'following verse'},
        }}
        original = copy.deepcopy(rows)
        self.assertEqual(normalize_known_joins(rows), ['ubh-matthew23-14-15'])
        self.assertNotIn('40:23:15', rows['ubh'])
        self.assertEqual(rows['ubh']['40:23:14']['last'], 15)
        passage = extract_passage({'book': 40, 'ranges': [[23, 13, 23, 16]]}, 'ubh', rows['ubh'], {'40': {'uk': 'Матея', 'uk_abbr': 'Мт'}}, 'uk')
        self.assertEqual([(v['first'], v['last']) for v in passage['verses']], [(13, 13), (14, 15), (16, 16)])
        self.assertEqual(sum(v['text'] == UBH_MATTHEW_23_14 for v in passage['verses']), 1)
        for mutation in ('text', 'missing', 'bounds'):
            changed = copy.deepcopy(original)
            if mutation == 'text': changed['ubh']['40:23:14']['text'] = 'unknown neighbour'
            if mutation == 'missing': del changed['ubh']['40:23:14']
            if mutation == 'bounds': changed['ubh']['40:23:14']['last'] = 16
            with self.subTest(mutation=mutation), self.assertRaises(BuildError): normalize_known_joins(changed)
        # A correctly joined source needs no rule; an independently missing verse still fails.
        self.assertEqual(normalize_known_joins(rows), [])
        del rows['ubh']['40:23:16']
        with self.assertRaises(BuildError): extract_passage({'book': 40, 'ranges': [[23, 13, 23, 16]]}, 'ubh', rows['ubh'], {'40': {'uk': 'Матея', 'uk_abbr': 'Мт'}}, 'uk')

    def test_fixture_renders_only_in_preview(self):
        from sitegen.build import SiteBuilder
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / 'content/bible-garden'
            shutil.copytree(ROOT / 'content/bible-garden', content)
            shutil.copytree(ROOT / 'tests/fixtures/gospel-today', content / 'articles/gospel-today-fixture')
            public = Path(directory) / 'public'
            preview = Path(directory) / 'preview'
            SiteBuilder(content, public, preview=False).build()
            self.assertFalse((public / 'ru/articles/gospel-today-fixture/index.html').exists())
            with patch.dict(os.environ, {'GOSPEL_AUDIO_BASE_URL': 'http://192.168.127.133:9084'}):
                SiteBuilder(content, preview, preview=True).build()
            for lang in ('ru', 'uk'):
                html = (preview / f'{lang}/articles/gospel-today-fixture/index.html').read_text()
                self.assertIn('src="/js/gospel-today.js"', html)
                self.assertIn('name="robots" content="noindex"', html)
                self.assertIn('data-gospel-today', html)
                self.assertIn('http://192.168.127.133:9084', html)
            existing = next((public / 'articles').glob('*/index.html')).read_text()
            self.assertNotIn('src="/js/gospel-today.js"', existing)

    def test_local_export_rejects_blank_source_without_writing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            shutil.copy2(SOURCE / 'tables.json', source / 'tables.json')
            with patch('tools.build_gospel_today.SOURCE', source), patch('tools.build_gospel_today.local_query', return_value=[['ubh', 40, 23, 16, 0, '']]):
                with self.assertRaisesRegex(BuildError, 'empty local text'):
                    export_local()
            self.assertFalse((source / 'verses.json').exists())

    def test_javascript_in_timezones(self):
        for zone in ('Pacific/Kiritimati', 'America/Los_Angeles', 'Europe/Kyiv'):
            completed = subprocess.run(['node', str(ROOT / 'tests/gospel_today.js')], env={**os.environ, 'TZ': zone}, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
