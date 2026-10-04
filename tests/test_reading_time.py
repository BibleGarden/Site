"""Reading-time source aggregation, strict marker and progressive HTML rendering."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from sitegen.content import load_site, parse_article
from sitegen.errors import BuildError
from sitegen.reading_time import LANGS, VOICES, DATA_PATH, PLACEHOLDER, annotate_calculator_marker, duration_label, load_data, render_calculator, validate_data
from tools.build_reading_time import DATA, VOICE_BOOKS, build_data, canonical_book, chapter_count, decode, mp3_payload, ranges, span_sum

ROOT = Path(__file__).resolve().parent.parent


class ReadingTimeArithmeticTest(unittest.TestCase):
    def test_app_units_include_first_block_and_titles(self):
        verses=[(1,0,False,False),(2,0,True,False),(3,0,False,True),(4,0,False,True)]
        self.assertEqual(ranges(verses,'paragraph'),[(0,0),(1,3)])
        self.assertEqual(ranges(verses,'section'),[(0,1),(2,2),(3,3)])
        self.assertEqual(ranges(verses,'chapter'),[(0,3)])
        with self.assertRaises(BuildError):
            ranges([], 'verse')

    def test_leading_audio_is_bounded_by_previous_end_and_file(self):
        audio=[(.1,1),(1.1,2),(2.5,10)]
        self.assertAlmostEqual(span_sum(audio,[(0,0),(1,1),(2,2)],5),4.7)
        self.assertAlmostEqual(span_sum(audio,[(0,2)],5),5)
        self.assertAlmostEqual(span_sum([(10,12)],[(0,0)],5),0)
        empty=[]
        self.assertEqual(span_sum([(1,2),(1.5,1.6)],[(1,1)],5,empty),0)
        self.assertEqual(empty,[(1,1,2,1.6)])
        with self.assertRaisesRegex(BuildError,'invalid alignment'):
            span_sum([(2,1)],[(0,0)],5)

    def test_book_order_and_chapter_schemes(self):
        self.assertEqual(canonical_book(45),59)
        self.assertEqual(canonical_book(52),45)
        self.assertEqual(chapter_count('ubh',39),3)
        self.assertEqual(chapter_count('bsb',39),4)
        self.assertEqual(chapter_count('syn',19),150)
        self.assertEqual(chapter_count('syn',27),12)

    def test_decoder_reports_bad_packets_and_fails_only_without_audio(self):
        with tempfile.NamedTemporaryFile() as source:
            for code, stderr, stdout in [(1,b'bad audio',b''),(0,b'corrupt audio',b'out_time_us=0'),(0,b'',b'')]:
                result=subprocess.CompletedProcess([],code,stdout,stderr)
                with patch('tools.build_reading_time.mp3_payload',return_value=(b'audio',0)), patch('tools.build_reading_time.subprocess.run',return_value=result), self.assertRaises(BuildError):
                    decode(Path(source.name))
            result=subprocess.CompletedProcess([],0,b'out_time_us=123000000',b'Header missing\nError submitting packet to decoder: Invalid data\nHeader missing\nError submitting packet to decoder: Invalid data\n')
            with patch('tools.build_reading_time.mp3_payload',return_value=(b'audio',0)), patch('tools.build_reading_time.subprocess.run',return_value=result):
                seconds,digest,packets,lines=decode(Path(source.name))
                self.assertEqual(seconds,123)
                self.assertEqual(packets,2)
                self.assertEqual(lines,4)
                with self.assertRaisesRegex(BuildError,'strict decoder error'):
                    decode(Path(source.name),strict=True)

    def test_id3_filter_preserves_audio_and_rejects_truncated_metadata(self):
        frame=b'\xff\xfb\x90\x00'+bytes(413)
        tag=b'ID3\x04\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf59.27.100'+bytes(11)
        payload, tags=mp3_payload(tag+frame+tag+frame)
        self.assertEqual(payload,frame+frame)
        self.assertEqual(tags,2)
        self.assertEqual(mp3_payload(frame+b'garbage')[0],frame+b'garbage')
        with self.assertRaises(BuildError):
            mp3_payload(tag[:-1])

    def test_marker_exact_unique_site_and_fences(self):
        marker='<!-- calculator: reading-time -->'
        body, found=annotate_calculator_marker('Before\n'+marker+'\nAfter',Path('article.md'),'bible-garden')
        self.assertTrue(found)
        self.assertIn(PLACEHOLDER,body)
        for value in (' '+marker,marker+marker,'<!-- calculator: other -->','<!-- Calculator: reading-time -->','<!-- calcualtor: reading-time -->','<!-- calculator: reading-time-->',marker+'\n'+marker):
            with self.subTest(marker=value), self.assertRaises(BuildError):
                annotate_calculator_marker(value,Path('article.md'),'bible-garden',7)
        with self.assertRaisesRegex(BuildError,'only supported'):
            annotate_calculator_marker(marker,Path('article.md'),'lampada')
        body, found=annotate_calculator_marker('```html\n'+marker+'\n```',Path('article.md'),'bible-garden')
        self.assertFalse(found)
        self.assertIn(marker,body)

    def test_javascript_formulas_and_calendar(self):
        subprocess.run(['node',str(ROOT/'tests/reading_time.js')],check=True,capture_output=True,text=True)


class ReadingTimeDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_data()

    def test_corrupt_data_stops_build(self):
        mutations=[lambda d: d.pop('method'),lambda d: d['voices'].pop('bsb_souer'),lambda d: d['books'].reverse(),lambda d: d['voices']['bsb_souer']['books']['1'].update(seconds=float('nan')),lambda d: d['voices']['bsb_souer']['books']['1'].update(chapters=49),lambda d: d['voices']['bsb_souer']['books']['1']['units']['verse'].update(count=-1),lambda d: d['voices']['bsb_souer']['books']['1']['units']['chapter'].update(seconds=1e9),lambda d: d['books'][0].update(chapters=True),lambda d: d['voices']['bsb_souer']['books']['1'].update(seconds=10**400),lambda d: d.update(translations={})]
        for change in mutations:
            data=copy.deepcopy(self.data)
            change(data)
            with self.subTest(change=change), self.assertRaises(BuildError):
                validate_data(data)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'reading-time.json'
            path.write_text('{"x":1,"x":2}')
            with self.assertRaisesRegex(BuildError,'duplicate JSON key'):
                load_data(path)
            with self.assertRaisesRegex(BuildError,'missing'):
                load_data(Path(directory)/'missing.json')

    def test_renderer_localized_table_controls_and_i18n(self):
        durations={'en':'3 years 3 months','ru':'3 года 3 месяца','uk':'3 роки 3 місяці'}
        for lang in ('en','ru','uk'):
            strings=yaml.safe_load((ROOT/f'content/bible-garden/i18n/{lang}.yaml').read_text())['articles']['reading_time']
            html=render_calculator(self.data,lang,strings)
            self.assertIn('aria-live="polite"',html)
            self.assertIn('class="reading-time-form" hidden',html)
            self.assertIn('<option value="" selected>',html)
            self.assertIn('class="reading-time-audio" hidden',html)
            self.assertIn(durations[lang],html)
            self.assertEqual(duration_label(1189,lang,strings),durations[lang])
            self.assertIn(self.data['measured_on'],html)
            self.assertNotIn('name="wpm"',html)
            self.assertNotIn('name="mode"',html)
            self.assertNotIn('name="book"',html)
            self.assertEqual(html.split('<tbody>')[1].split('</tbody>')[0].count('<tr>'),6)
            bad=dict(strings);bad.pop('title')
            with self.assertRaisesRegex(BuildError,'i18n'):
                render_calculator(self.data,lang,bad)
            bad=dict(strings);bad['result']='{unknown}'
            with self.assertRaisesRegex(BuildError,'i18n template'):
                render_calculator(self.data,lang,bad)
        data=copy.deepcopy(self.data)
        data['voices']['bsb_souer']['names']['en']='</script><b>bad</b>'
        html=render_calculator(data,'en',strings=yaml.safe_load((ROOT/'content/bible-garden/i18n/en.yaml').read_text())['articles']['reading_time'])
        self.assertNotIn('</script><b>bad</b>',html)
        self.assertIn('\\u003c/script>',html)

    def test_article_integration_does_not_add_faq(self):
        site=load_site(ROOT/'content/bible-garden',ROOT)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'en.md'
            source.write_text('---\ntitle: Test\ndescription: Test calculator\ndate: 2026-10-04\ndraft: true\n---\n<!-- calculator: reading-time -->\n')
            with patch('sitegen.content.load_reading_time',return_value=self.data):
                article=parse_article(source,'test','en',{}, {},site.i18n['en']['articles'],Path(directory))
            self.assertTrue(article.has_calculator)
            self.assertFalse(article.faq)
            self.assertIn('class="reading-time"',article.body_html)
            self.assertNotIn(PLACEHOLDER,article.body_html)


class ReadingTimeCommittedDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=load_data()

    def test_rebuild_is_identical_and_coverage_is_explicit(self):
        self.assertEqual(build_data(),self.data)
        self.assertNotIn('translations',self.data)
        self.assertFalse((DATA/'translations.tsv').exists())
        self.assertEqual(sum(b['chapters'] for b in self.data['books']),1189)
        self.assertEqual(sum(b['chapters'] for b in self.data['books'] if b['id']<=39),929)
        self.assertEqual(len(self.data['voices']['bondarenko']['books']),62)
        self.assertEqual(len(self.data['voices']['npu_uk']['books']),28)
        webbe=sum(b['seconds'] for b in self.data['voices']['web_british']['books'].values())/3600
        self.assertAlmostEqual(webbe,66.23,delta=.02)

    def test_manifest_decoder_sample_and_anomaly_report(self):
        import csv
        manifest=json.loads((DATA/'manifest.json').read_text())
        self.assertEqual(manifest['chapter_count'],9782)
        self.assertEqual(len(manifest['strict_sample']),9)
        for sample in manifest['strict_sample']:
            self.assertEqual(sample['normal_seconds'],sample['strict_seconds'])
        with (DATA/'alignment-anomalies.tsv').open() as handle:
            anomalies=list(csv.DictReader(handle,delimiter='\t'))
        for kind,count in manifest['anomaly_counts'].items():
            self.assertEqual(sum(r['type']==kind for r in anomalies),count)
        empty={(r['voice'],int(r['book']),int(r['chapter']),int(r['first_verse'])) for r in anomalies if r['type']=='empty_window'}
        self.assertEqual(empty,{('bondarenko',2,1,21),('bondarenko',2,18,14),('winfred_henson',1,15,15),('prozorovsky',2,16,34),('prozorovsky',18,24,3)})
        errors=[r for r in anomalies if r['type']=='decoder_errors']
        self.assertEqual(len(errors),12)
        self.assertTrue(all(r['voice']=='bsb_david' and int(r['bad_packets'])>0 for r in errors))
        self.assertEqual(sum(int(r['bad_packets']) for r in errors),manifest['bad_packets'])

    def test_tsv_checksum_and_missing_chapters_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            for item in DATA.iterdir():
                (path/item.name).write_bytes(item.read_bytes())
            (path/'voices.tsv').write_text((path/'voices.tsv').read_text()+'bad\n')
            with patch('tools.build_reading_time.DATA',path), self.assertRaisesRegex(BuildError,'checksum mismatch'):
                build_data()
            import hashlib
            original=(DATA/'voices.tsv').read_text().splitlines(keepends=True)
            (path/'voices.tsv').write_text(''.join(original[:-1]))
            manifest=json.loads((path/'manifest.json').read_text())
            manifest['files']['voices.tsv']=hashlib.sha256((path/'voices.tsv').read_bytes()).hexdigest()
            (path/'manifest.json').write_text(json.dumps(manifest))
            with patch('tools.build_reading_time.DATA',path), self.assertRaisesRegex(BuildError,'chapter coverage mismatch'):
                build_data()



if __name__=='__main__':
    unittest.main()
