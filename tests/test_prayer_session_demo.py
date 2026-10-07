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
        return self.site.i18n[lang]['prayer_demo']

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
            lambda d: d['locales']['en']['audio'].update(narrator=''),
            lambda d: d['locales']['en']['audio'].update(license=''),
            lambda d: d['locales']['uk']['audio'].update(source_file='audio/npu/npu_uk/mp3/19/117.mp3'),
            lambda d: d['locales']['uk']['audio'].update(license_url='javascript:bad'),
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
            self.assertIn(html.escape(self.strings(lang)['keep_flame']), result)
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
                article = parse_article(source, 'demo', lang, {}, {}, self.site.i18n[lang]['articles'], Path(directory), site_key='lampada', prayer_strings=self.strings(lang))
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

    def test_plurals_and_structure_are_not_pinned_to_the_scenario(self):
        from sitegen.prayer_session_demo import week_label
        self.assertIn('2 дня', week_label('ru', self.strings('ru'), 2))
        self.assertIn('5 днів', week_label('uk', self.strings('uk'), 5))
        self.assertIn('1 day', week_label('en', self.strings(), 1))
        data = copy.deepcopy(self.data)
        data['week'] = [False]*7
        validate_demo(data, Path('demo.json'))
        self.assertEqual(week_label('ru', self.strings('ru'), 0), '')
        data['locales']['en']['audio']['license_url'] = 'https://publisher.example/permission'
        data['locales']['en']['audio']['narrator'] = 'Another attributed narrator'
        validate_demo(data, Path('demo.json'))
        data['locales']['ru']['audio'] = copy.deepcopy(data['locales']['en']['audio'])
        with self.assertRaisesRegex(BuildError, 'owner decision'):
            validate_demo(data, Path('demo.json'))

    def test_rendered_article_conditionally_loads_component_assets(self):
        from sitegen.build import SiteBuilder
        with tempfile.TemporaryDirectory() as directory:
            builder = SiteBuilder(ROOT / 'content/lampada', Path(directory) / 'site', preview=False)
            source = Path(directory) / 'demo.md'
            header = '---\ntitle: Demo\ndescription: Example\ndate: 2026-10-07\n---\n\n'
            for body in ('<!-- demo: prayer-session -->', 'Plain article'):
                source.write_text(header + body)
                article = parse_article(source, 'demo', 'en', {}, {}, self.site.i18n['en']['articles'], Path(directory),
                                        site_key='lampada', prayer_strings=self.strings())
                builder.articles = {'demo': {'en': article}}
                builder.build_article('demo', 'en')
                rendered = (builder.site.output_dir / 'articles/demo/index.html').read_text()
                for asset in ('prayer-session-demo.css', 'prayer-session-demo.js'):
                    self.assertEqual(asset in rendered, article.has_prayer_demo)
                self.assertEqual('data-prayer-demo' in rendered, article.has_prayer_demo)

    def test_public_notices_and_template_js_bindings(self):
        js = (ROOT / 'static/lampada/assets/prayer-session-demo.js').read_text()
        self.assertIsNone(re.search(r'\b(fetch|sendBeacon|XMLHttpRequest|localStorage|sessionStorage|indexedDB)\b', js))
        for lang in ('en','ru','uk'):
            rendered = render_demo(self.data, lang, self.strings(lang))
            for key in re.findall(r'root\.dataset\.(\w+)', js):
                attr = re.sub(r'([A-Z])', lambda m: '-'+m[1].lower(), key)
                self.assertIn(f'data-{attr}=', rendered, key)
            for attr in ('listen-label','pause-label','resume-label'):
                self.assertIn(f'data-{attr}=',rendered)
            self.assertIn('href="/assets/licenses/"',rendered)
            self.assertRegex(rendered, r'<dialog[^>]+data-answer-dialog[\s\S]*?data-answer-status[\s\S]*?</dialog>')
            self.assertNotRegex(rendered, r'123pfqn|86cbj|9015827487|/root/cep')
            if lang == 'ru':
                self.assertNotIn('Перевод и запись:',rendered)
                self.assertNotIn('право на распространение', rendered)
        for path in (ROOT / 'static/lampada/assets/licenses').glob('*'):
            self.assertNotRegex(path.read_text(), r'123pfqn|86cbj|9015827487|/root/cep|content/lampada')
        self.assertEqual({p.stem for p in (ROOT / 'static/lampada/assets/fonts').iterdir()},
                         set(__import__('sitegen.prayer_session_demo', fromlist=['FONTS']).FONTS))
        self.assertTrue(all(p.suffix == '.woff2' for p in (ROOT / 'static/lampada/assets/fonts').iterdir()))

    def test_audio_metadata_and_cut_tool_errors(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('prayer_audio_tool', ROOT / 'tools/build_prayer_demo_audio.py')
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with self.assertRaisesRegex(ValueError, 'missing id 118'):
            tool.find_by_id([], 118, 'chapter')
        for value in self.data['locales'].values():
            if value['audio']['status'] == 'available':
                self.assertNotIn(b'TSSE', (ROOT / 'static/lampada' / value['audio']['path'].lstrip('/')).read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parser = root / 'parser'
            value = copy.deepcopy(self.data['locales']['en'])
            text = parser / value['scripture']['source']
            text.parent.mkdir(parents=True)
            text.write_text(json.dumps({'books':[{'id':19, 'chapters':[{'id':118, 'verses':[{'id':24, 'unformatedText':value['scripture']['text']}]}]}]}))
            source = parser / value['audio']['source_file']
            source.parent.mkdir(parents=True)
            source.write_bytes(b'test recording')
            value['audio']['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            (source.parents[2] / 'timecodes.json').write_text(json.dumps({'books':[{'id':19, 'chapters':[{'id':118, 'verses':[{'id':24, 'begin':0,'end':1}]}]}]}))
            manifest = root / 'content/lampada/demos/prayer-session.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'locales':{'en':value}}))
            with patch.object(tool,'ROOT',root), patch.object(tool.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'differs from source timecodes'):
                    tool.build(parser)
                run.assert_not_called()

    def test_js_flow_and_audio(self):
        subprocess.run(['node', str(ROOT / 'tests/prayer_session_demo.js')], check=True)
