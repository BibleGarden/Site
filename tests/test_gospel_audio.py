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
from sitegen.gospel_audio import EDITIONS
from tools.export_gospel_timecodes import export_timecodes


class GospelAudioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.assets = load_bundle()

    def test_every_edition_and_voice_is_explicit_and_apostle_is_aligned(self):
        self.assertEqual(len(EDITIONS), 7)
        self.assertEqual(sum(len(e['voices']) for e in EDITIONS.values()), 9)
        for translation, edition in EDITIONS.items():
            passages = self.assets[f'{translation}/texts.json']['passages']
            for p in passages.values():
                if 'unavailable' not in p: validate_audio(p, translation)
            self.assertTrue(any(p['book'] >= 45 and p.get('audio',{}).get(next(iter(edition['voices']))) for p in passages.values()))
        for base in ('static', 'dist', '.preview'):
            self.assertFalse(list((ROOT / base / 'bible-garden/audio/demo/gospel-today').rglob('*.mp3')))

    def test_joined_verse_coverage_and_no_voice_substitution(self):
        passages = self.assets['ubh/texts.json']['passages']
        merged = next(p for p in passages.values() if p['book'] == 40 and p['ranges'] == [[23, 13, 23, 22]])
        self.assertIn((14,15), [(v['first'],v['last']) for v in merged['verses']])
        index = next(i for i,v in enumerate(merged['verses']) if v['first'] == 14)
        self.assertEqual(merged['audio']['kozlov_uk'][index], load_json(SOURCE / 'timecodes.json')['timecodes']['kozlov_uk']['40:23:14'])
        self.assertFalse(any(v['first'] == 15 for v in merged['verses']))
        npu = self.assets['npu/texts.json']['passages']
        self.assertTrue(all(p.get('unavailable') == 'missing_text' for p in npu.values() if p['book'] < 40 and p['book'] != 19))
        syn = self.assets['syn/texts.json']['passages']
        isaiah = next(p for p in syn.values() if p['book'] == 23)
        self.assertIsNone(isaiah['audio']['bondarenko'])
        self.assertIsNotNone(isaiah['audio']['prudovsky'])
        bti = self.assets['bti/texts.json']['passages']
        self.assertTrue(any(p.get('unavailable') == 'numbering' for p in bti.values()))

    def test_missing_timecode_marks_only_affected_voice_unavailable(self):
        snapshot = load_json(SOURCE / 'timecodes.json')
        source = next(p for p in self.assets['syn/texts.json']['passages'].values() if p['book'] == 40)
        passage = copy.deepcopy(source)
        verse = passage['verses'][0]
        key = f"{passage['book']}:{verse['chapter']}:{verse['first']}"
        del snapshot['timecodes']['prudovsky'][key]
        attach_audio({'p': passage}, 'syn', snapshot)
        self.assertIsNone(passage['audio']['prudovsky'])
        self.assertEqual(passage['audio']['bondarenko'], source['audio']['bondarenko'])

    def test_export_rejects_registry_changes_duplicates_and_corrupt_timings(self):
        registry = [[v,t] for t,e in EDITIONS.items() for v in e['voices']]
        for rows, message in [([['prudovsky',40,1,1,0,float('nan')]], 'invalid alignment'),
                              ([['prudovsky',40,1,1,0,1]]*2, 'duplicate alignment')]:
            with patch('tools.export_gospel_timecodes.local_query', side_effect=[registry,rows]), self.assertRaisesRegex(BuildError, message):
                export_timecodes()
        with patch('tools.export_gospel_timecodes.local_query', return_value=[]), self.assertRaisesRegex(BuildError, 'registry changed'):
            export_timecodes()

    def test_wrong_voice_and_invalid_times_fail(self):
        source = next(p for p in self.assets['syn/texts.json']['passages'].values() if p['book'] == 40)
        for mutation in ('voice','time','missing','nan','bool'):
            p = copy.deepcopy(source)
            if mutation == 'voice': p['audio']['unknown'] = p['audio'].pop('prudovsky')
            if mutation == 'time': p['audio']['prudovsky'][0][1] = p['audio']['prudovsky'][0][0]
            if mutation == 'missing': p['audio']['prudovsky'].pop()
            if mutation == 'nan': p['audio']['prudovsky'][0][0] = float('nan')
            if mutation == 'bool': p['audio']['prudovsky'][0][0] = False
            with self.subTest(mutation=mutation), self.assertRaises(BuildError): validate_audio(p,'syn')

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
