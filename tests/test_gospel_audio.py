"""Chapter-stream metadata, read-only coverage and browser playback contract."""
import copy
import os
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sitegen.errors import BuildError
from sitegen.lectionary_data import ROOT, BUNDLE_DIR, load_bundle, SOURCE, load_json, encoded, digest
from sitegen.gospel_audio import attach_audio, validate_audio, validate_config, preview_config
from tools.export_gospel_timecodes import requirements, audit, gospel_ids


class GospelAudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.assets = load_bundle()

    def test_every_required_gospel_verse_has_timecodes_without_audio_binaries(self):
        needed = requirements(self.assets, 2026, 2030)
        snapshot = load_json(SOURCE / 'timecodes.json')
        self.assertEqual([len(needed[l]) for l in ('ru', 'uk')], [3453, 3452])
        for lang in ('ru', 'uk'):
            self.assertEqual(set(snapshot['timecodes'][lang]), set(needed[lang]))
            for passage in self.assets[f'{lang}/texts.json']['passages'].values():
                validate_audio(passage, lang)
        for base in ('static', 'dist', '.preview'):
            self.assertFalse(list((ROOT / base / 'bible-garden/audio/demo/gospel-today').rglob('*.mp3')))

    def test_merged_verse_and_composite_chapter_order(self):
        passages = self.assets['uk/texts.json']['passages']
        merged = next(p for p in passages.values() if p['book'] == 40 and p['ranges'] == [[23, 13, 23, 22]])
        pairs = [(v['first'], v['last'], s) for v, s in zip(merged['verses'], merged['audio']['segments'])]
        timing = load_json(SOURCE / 'timecodes.json')['timecodes']['uk']['40:23:14']
        self.assertIn((14, 15, {'chapter': 23, 'begin': timing[0], 'end': timing[1]}), pairs)
        self.assertFalse(any(first == 15 for first, last, segment in pairs))
        ids = gospel_ids(self.assets['ru/2026.json']['days']['2026-04-09']['items'])
        sequence = [(self.assets['ru/texts.json']['passages'][pid]['book'],
                     self.assets['ru/texts.json']['passages'][pid]['audio']['chapters'][0]) for pid in ids]
        self.assertEqual(sequence, [(40, 26), (43, 13), (40, 26), (42, 22), (40, 26)])
        cross = next(p for p in passages.values() if p['audio'] and len(p['audio']['chapters']) > 1)
        self.assertEqual(cross['audio']['chapters'], list(dict.fromkeys(v['chapter'] for v in cross['verses'])))

    def test_missing_timecodes_are_reported_together(self):
        snapshot = load_json(SOURCE / 'timecodes.json')
        passages = copy.deepcopy(self.assets['ru/texts.json']['passages'])
        keys = list(snapshot['timecodes']['ru'])[:2]
        for key in keys:
            del snapshot['timecodes']['ru'][key]
        with self.assertRaises(BuildError) as raised:
            attach_audio(passages, 'ru', snapshot)
        for key in keys:
            self.assertIn(key, str(raised.exception))

    def test_generator_reports_gaps_for_both_languages(self):
        from tools.build_gospel_today import generate
        snapshot = copy.deepcopy(load_json(SOURCE / 'timecodes.json'))
        removed = {lang: next(iter(snapshot['timecodes'][lang])) for lang in ('ru', 'uk')}
        for lang, key in removed.items():
            del snapshot['timecodes'][lang][key]
        def data(path):
            return snapshot if Path(path).name == 'timecodes.json' else load_json(path)
        with patch('tools.build_gospel_today.load_json', side_effect=data), self.assertRaises(BuildError) as raised:
            generate()
        for lang, key in removed.items():
            self.assertIn(lang, str(raised.exception))
            self.assertIn(key, str(raised.exception))

    def test_build_bundle_reports_all_missing_timecodes(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / 'lectionary'
            shutil.copytree(BUNDLE_DIR, bundle)
            manifest = load_json(bundle / 'manifest.json')
            coordinates = []
            for lang in ('ru', 'uk'):
                name = f'{lang}/texts.json'
                data = load_json(bundle / name)
                passage = next(p for p in data['passages'].values() if p['audio'])
                verse = passage['verses'][0]
                coordinates.append(f"{lang} {passage['book']}:{verse['chapter']}:{verse['first']}")
                passage['audio']['segments'][0] = None
                payload = encoded(data)
                (bundle / name).write_bytes(payload)
                manifest['files'][name] = digest(payload)
            (bundle / 'manifest.json').write_bytes(encoded(manifest))
            with self.assertRaises(BuildError) as raised:
                load_bundle(bundle)
            for coordinate in coordinates:
                self.assertIn(coordinate, str(raised.exception))

    def test_export_audit_reports_every_affected_day(self):
        needed = {'ru': {'40:1:1': {'2026-01-01', '2030-12-31'}, '40:1:2': {'2026-01-02'}},
                  'uk': {'40:1:1': {'2027-01-01'}}}
        with self.assertRaises(BuildError) as raised:
            audit(needed, [])
        text = str(raised.exception)
        self.assertEqual(text.count('missing timecode'), 3)
        for date in ('2026-01-01', '2026-01-02', '2027-01-01', '2030-12-31'):
            self.assertIn(date, text)
        for bounds in ((0, 0), (-1, 1), (0, float('nan')), (False, 1)):
            with self.subTest(bounds=bounds), self.assertRaises(BuildError):
                audit({'ru': {'40:1:1': {'2026-01-01'}}}, [('prudovsky', 40, 1, 1, *bounds)])
        with self.assertRaisesRegex(BuildError, 'duplicate timing'):
            audit({}, [('prudovsky', 40, 1, 1, 0, 1)] * 2)

    def test_wrong_voice_chapter_and_invalid_times_fail(self):
        source = next(p for p in self.assets['ru/texts.json']['passages'].values() if p['book'] == 40)
        for mutation in ('voice', 'translation', 'time', 'chapter', 'missing', 'nan'):
            p = copy.deepcopy(source)
            if mutation == 'voice': p['audio']['voice'] = 'kozlov_uk'
            if mutation == 'translation': p['audio']['translation'] = 'ubh'
            if mutation == 'time': p['audio']['segments'][0]['end'] = p['audio']['segments'][0]['begin']
            if mutation == 'chapter': p['audio']['segments'][0]['chapter'] = 99
            if mutation == 'missing': p['audio']['segments'].pop()
            if mutation == 'nan': p['audio']['segments'][0]['begin'] = float('nan')
            with self.subTest(mutation=mutation), self.assertRaises(BuildError):
                validate_audio(p, 'ru')

    def test_config_is_required_strict_and_overrides_are_explicit(self):
        good = {'base_url': 'https://api.bible.garden', 'site_key': 'public-test-key'}
        self.assertEqual(validate_config(good), good)
        for bad in (None, {}, {**good, 'site_key': ''}, {**good, 'base_url': 'ftp://example.com'},
                    {**good, 'base_url': 'http://example.com'}, {**good, 'base_url': 'https://a:b@example.com'},
                    {**good, 'base_url': 'https://example.com/?key=oops'}, {**good, 'base_url': 'https://x:bad'}, {**good, 'base_url': 'https://@example.com'},
                    {**good, 'base_url': 'https://bad host'},
                    {**good, 'site_key': ' whitespace '}, {**good, 'unknown': True}):
            with self.subTest(bad=bad), self.assertRaises(BuildError):
                validate_config(bad)
        with patch.dict(os.environ, {'GOSPEL_AUDIO_BASE_URL': 'http://127.0.0.1:8000', 'GOSPEL_AUDIO_SITE_KEY': 'test-key'}):
            self.assertEqual(preview_config(good), {'base_url': 'http://127.0.0.1:8000', 'site_key': 'test-key'})
            self.assertEqual(validate_config(good), good)
        with patch.dict(os.environ, {'GOSPEL_AUDIO_SITE_KEY': ''}), self.assertRaises(BuildError):
            preview_config(good)

    def test_http_is_preview_only_and_private_ipv4_is_exactly_rfc1918(self):
        config = {'base_url': 'https://api.bible.garden', 'site_key': 'explicit-test-key'}
        allowed = ('localhost', '127.0.0.1', '127.255.255.254', '[::1]',
                   '10.0.0.0', '10.255.255.255', '172.16.0.0', '172.31.255.255',
                   '192.168.0.0', '192.168.255.255', '192.168.127.133')
        rejected = ('9.255.255.255', '11.0.0.0', '172.15.255.255', '172.32.0.0',
                    '192.167.255.255', '192.169.0.0', '8.8.8.8', '100.64.0.1',
                    '169.254.1.1', '192.0.0.1', '0.0.0.0', '[fc00::1]', '[fe80::1]',
                    'dev.example.com', '192.168.1.1.example.com')
        for host in allowed + rejected:
            http = {**config, 'base_url': f'http://{host}:9084'}
            with self.subTest(host=host), self.assertRaises(BuildError):
                validate_config(http)
            with self.subTest(host=host, preview=True):
                if host in allowed:
                    self.assertEqual(validate_config(http, preview=True), http)
                else:
                    with self.assertRaises(BuildError):
                        validate_config(http, preview=True)

    def test_preview_overrides_never_change_production_config(self):
        from sitegen.content import load_site
        with patch.dict(os.environ, {'GOSPEL_AUDIO_BASE_URL': 'http://192.168.127.133:9084',
                                    'GOSPEL_AUDIO_SITE_KEY': 'explicit-preview-test-key'}):
            public = load_site(ROOT / 'content/bible-garden', ROOT)
            preview = load_site(ROOT / 'content/bible-garden', ROOT, preview=True)
        self.assertEqual(public.config['gospel_audio']['base_url'], 'https://api.bible.garden')
        self.assertNotEqual(public.config['gospel_audio']['site_key'], 'explicit-preview-test-key')
        self.assertEqual(preview.config['gospel_audio'],
                         {'base_url': 'http://192.168.127.133:9084', 'site_key': 'explicit-preview-test-key'})

    def test_player_harness(self):
        result = subprocess.run(['node', str(ROOT / 'tests/gospel_audio.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
