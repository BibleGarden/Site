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
from sitegen.lectionary_data import (ROOT, SOURCE, BUNDLE_DIR, load_bundle, validate_passages, validate_schedule, public_files, validate_month, validate_chapter, referenced_passages)
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

    def test_public_files_are_chapter_bounded_and_strict(self):
        from sitegen.gospel_audio import EDITIONS
        manifest, assets = load_bundle()
        files=public_files(manifest,assets)
        self.assertEqual(sum(name.startswith('schedule/') for name in files),120)
        self.assertEqual(sum(name.startswith('text/') for name in files),2198)
        for name,payload in files.items():
            data=json.loads(payload)
            if name.startswith('schedule/'):
                _,lang,year,month=name.split('/')
                validate_month(data,lang,int(year),int(month[:-5]))
                self.assertEqual(data['days'],{date:day for date,day in assets[f'{lang}/{year}.json']['days'].items() if date[5:7]==month[:-5]})
                self.assertNotIn('text',payload.decode())
            else:
                _,translation,book,chapter=name.split('/')
                validate_chapter(data,translation,int(book),int(chapter[:-5]))
            self.assertEqual((ROOT/'dist/bible-garden/data/gospel-today'/name).read_bytes(),payload)
        schedule=json.loads(files['schedule/ru/2028/02.json'])
        self.assertIn('2028-02-29',schedule['days'])
        for mutate in ('missing_day','unused_ref','wrong_calendar','wrong_month'):
            value=copy.deepcopy(schedule)
            if mutate=='missing_day':del value['days']['2028-02-29']
            if mutate=='unused_ref':value['references']['unused']={'book':1,'ranges':[[1,1,1,1]]}
            if mutate=='wrong_calendar':value['calendar']='newjulian'
            if mutate=='wrong_month':value['month']=3
            with self.subTest(mutate=mutate),self.assertRaises(BuildError):validate_month(value,'ru',2028,2)
        chapter=json.loads(files['text/syn/40/01.json'])
        for mutate in ('wrong_translation','bad_text','bad_timing','missing_voice','duplicate_verse','bad_availability'):
            value=copy.deepcopy(chapter)
            if mutate=='wrong_translation':value['translation']='ubh'
            if mutate=='bad_text':value['verses'][0][2]=''
            if mutate=='bad_timing':value['audio']['prudovsky'][0]=[1,1]
            if mutate=='missing_voice':del value['audio']['bondarenko']
            if mutate=='duplicate_verse':value['verses'][1]=value['verses'][0]
            if mutate=='bad_availability':value['unavailable']='missing_text'
            with self.subTest(mutate=mutate),self.assertRaises(BuildError):validate_chapter(value,'syn',40,1)

    def test_passage_missing_text_and_schedule_missing_day_fail(self):
        _, assets = load_bundle()
        texts = copy.deepcopy(assets['syn/texts.json'])
        passage = next(p for p in texts['passages'].values() if 'verses' in p)
        passage['verses'][0]['text'] = ''
        with self.assertRaises(BuildError): validate_passages(texts, 'ru')
        schedule = copy.deepcopy(assets['uk/2026.json']); del schedule['days']['2026-01-01']
        with self.assertRaises(BuildError): validate_schedule(schedule, 'uk', 2026, assets['ubh/texts.json']['passages'])
        schedule = copy.deepcopy(assets['uk/2026.json'])
        schedule['days']['2026-01-01']['uncertain'] = False
        schedule['days']['2026-01-01']['confirmed_by'] = []
        with self.assertRaises(BuildError): validate_schedule(schedule, 'uk', 2026, assets['ubh/texts.json']['passages'])

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
