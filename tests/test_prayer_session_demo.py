"""Lampada validation, no-JS rendering, article integration and real JS behavior."""
import copy
import hashlib
import html
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from sitegen.assets import version_html
from sitegen.content import load_site, parse_article
from sitegen.demo_markers import annotate_demo_marker
from sitegen.errors import BuildError
from sitegen.prayer_session_demo import DEMOS_DIR, ROOT, load_demo, render_demo, validate_demo


class PrayerDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_demo()
        cls.site = load_site(ROOT / 'content/lampada', ROOT)

    def strings(self, lang='en'):
        return self.site.i18n[lang]['articles']['prayer_demo']

    def test_strict_markers_and_fences(self):
        body, name = annotate_demo_marker('<!-- demo: prayer-session -->', Path('demo.md'), 'lampada')
        self.assertEqual(name, 'prayer-session')
        self.assertIn('data-demo-placeholder', body)
        for body in (' <!-- demo: prayer-session -->', '<!-- demmo: prayer-session -->',
                     '<!-- demo: missing -->', '<!-- demo: multi-reading -->',
                     '<!-- demo: prayer-session -->\n<!-- demo: prayer-session -->'):
            with self.subTest(body=body), self.assertRaisesRegex(BuildError, r'demo.md:12:|demo.md:13:'):
                annotate_demo_marker(body, Path('demo.md'), 'lampada', 12)
        for fence in ('```', '~~~'):
            _, name = annotate_demo_marker(f'{fence}\n<!-- demo: missing -->\n{fence}', Path('demo.md'), 'lampada')
            self.assertIsNone(name)
        with self.assertRaises(BuildError):
            annotate_demo_marker('<!-- demo: prayer-session -->', Path('demo.md'), 'bible-garden')

    def test_invalid_manifest_fails_loudly(self):
        mutations = [
            lambda d: d.update(extra=True), lambda d: d['timer'].update(remaining=True),
            lambda d: d['timer'].update(remaining=301), lambda d: d['locales'].pop('uk'),
            lambda d: d['week'].append(True), lambda d: d['locales']['en'].update(goal=''),
            lambda d: d['locales']['en'].update(questions=['one']),
            lambda d: d['locales']['en']['scripture'].update(translation='webus'),
            lambda d: d['locales']['en']['audio'].update(path='/missing.mp3'),
            lambda d: d['locales']['en']['audio'].update(sha256='0'*64),
            lambda d: d['locales']['en']['audio'].update(duration=float('nan')),
            lambda d: d['locales']['en']['audio'].update(narrator='Unconfirmed'),
            lambda d: d['locales']['en']['audio'].update(license='Unconfirmed'),
            lambda d: d['locales']['uk']['audio'].update(source_file='audio/npu/npu_uk/mp3/19/117.mp3'),
            lambda d: d['locales']['uk']['audio'].update(license_url='https://unverified.example/'),
            lambda d: d['locales']['ru'].update(audio=None),
            lambda d: d['locales']['ru']['audio'].update(reason=''),
        ]
        for mutation in mutations:
            data = copy.deepcopy(self.data)
            mutation(data)
            with self.subTest(mutation=mutation), self.assertRaises(BuildError):
                validate_demo(data, Path('demo.json'))
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(BuildError):
            validate_demo(self.data, Path('demo.json'), Path(directory))

    def test_json_duplicates_constants_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'demo.json'
            for text in ('{"kind":"prayer-session","kind":"other"}', '{"timer":NaN}', '{'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(BuildError):
                    load_demo('demo', Path(directory))
            with self.assertRaises(BuildError):
                load_demo('missing', Path(directory))
            with self.assertRaises(BuildError):
                load_demo('../demo', Path(directory))

    def test_static_screen_translations_and_audio_rights(self):
        for lang in ('en','ru','uk'):
            result = render_demo(self.data, lang, self.strings(lang))
            self.assertIn(html.escape(self.data['locales'][lang]['scripture']['text']), result)
            self.assertIn(html.escape(self.strings(lang)['lit']), result)
            self.assertIn('class="pd-static"', result)
            self.assertIn('data-screen="home"', result)
            self.assertNotIn('class="pd-ready"', result)
            self.assertIn('data-action="start" disabled', result)
            self.assertIn('data-screen="session" hidden', result)
            self.assertIn('data-screen="reflect" hidden', result)
            self.assertIn('<dialog ', result)
            self.assertEqual(result.count('data-player'), 0 if lang == 'ru' else 1)
            if lang == 'ru':
                self.assertIn(self.strings(lang)['audio_unavailable'], result)
            else:
                self.assertIn('preload="none"', result)
                self.assertIn(self.data['locales'][lang]['audio']['license_url'], result)
            ids = re.findall(r'\bid="([^"]+)"', result)
            self.assertEqual(len(ids), len(set(ids)))
            for ref in re.findall(r'aria-(?:controls|labelledby)="([^"]+)"', result):
                self.assertIn(ref, ids)

    def test_escaping_and_required_labels(self):
        data = copy.deepcopy(self.data)
        payload = '<script>alert("x")</script>'
        data['locales']['en']['questions'][0] = payload
        rendered = render_demo(data, 'en', self.strings())
        self.assertNotIn(payload, rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn(payload, html.unescape(rendered))
        self.assertIn('\\u003cscript\\u003e', rendered)
        for key in self.strings():
            labels = dict(self.strings()); labels.pop(key)
            with self.subTest(key=key), self.assertRaises(BuildError):
                render_demo(self.data, 'en', labels)
        with self.assertRaises(BuildError):
            render_demo(self.data, 'fr', self.strings())

    def test_article_uses_the_same_renderer_and_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'demo.md'
            source.write_text('---\ntitle: Demo\ndescription: Example\ndate: 2026-10-07\n---\n\n<!-- demo: prayer-session -->\n')
            for lang in ('en','ru','uk'):
                article = parse_article(source, 'demo', lang, {}, {}, self.site.i18n[lang]['articles'], Path(directory), site_key='lampada')
                self.assertTrue(article.has_prayer_demo)
                self.assertFalse(article.has_demo)
                self.assertIn(render_demo(self.data,lang,self.strings(lang)), article.body_html)
                self.assertNotIn('data-demo-placeholder', article.body_html)
                self.assertEqual(article.faq, ())

    def test_new_asset_urls_use_content_hashes(self):
        for name in ('prayer-session-demo.css', 'prayer-session-demo.js'):
            path = ROOT / 'static/lampada/assets' / name
            tag = f'<script src="/assets/{name}"></script>'
            expected = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            self.assertIn(f'{name}?v={expected}', version_html(tag, ROOT / 'static/lampada/index.html', ROOT / 'static/lampada', 'https://lampada.app'))

    def test_js_flow_and_audio(self):
        subprocess.run(['node', str(ROOT / 'tests/prayer_session_demo.js')], check=True)
