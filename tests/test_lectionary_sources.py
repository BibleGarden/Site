"""Service classification of captured Ukrainian calendar readings."""
import copy
import unittest

from sitegen.errors import BuildError
from sitegen.lectionary_data import SOURCE, load_json
from tools.build_lectionary_references import liturgy_refs, rebuild


class SourceReadingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshots = load_json(SOURCE / 'source-readings.json')
        cls.references = load_json(SOURCE / 'references.json')

    def lines(self, source, date):
        return next(d['lines'] for d in self.snapshots[source] if d['date'] == date)

    def test_offline_extraction_reproduces_committed_evidence(self):
        self.assertEqual(rebuild(copy.deepcopy(self.references), self.snapshots), self.references)
        changed = copy.deepcopy(self.snapshots)
        changed['ocu'][0]['date'] = '2027-01-01'
        with self.assertRaisesRegex(BuildError, 'captured dates changed'):
            rebuild(copy.deepcopy(self.references), changed)
        changed = copy.deepcopy(self.snapshots)
        changed['ocu'][0]['lines'][0]['refs'] = []
        with self.assertRaisesRegex(BuildError, 'comparison refs changed'):
            rebuild(copy.deepcopy(self.references), changed)

    def test_ordinary_pair_without_heading(self):
        expected = [{'book': 50, 'ranges': [[1, 1, 1, 7]]},
                    {'book': 42, 'ranges': [[4, 37, 4, 44]]}]
        for source in ('ocu', 'ugcc'):
            with self.subTest(source=source):
                self.assertEqual(liturgy_refs(source, self.lines(source, '2026-10-05')), expected)

    def test_explicit_liturgy_excludes_other_services(self):
        expected = [{'book': 56, 'ranges': [[2, 11, 2, 14], [3, 4, 3, 7]]},
                    {'book': 40, 'ranges': [[3, 13, 3, 17]]}]
        for source in ('ocu', 'ugcc'):
            with self.subTest(source=source):
                self.assertEqual(liturgy_refs(source, self.lines(source, '2026-01-06')), expected)
                # Royal Hours precede Liturgy; water blessing follows it (OCU).
                self.assertEqual(liturgy_refs(source, self.lines(source, '2026-01-05')),
                                 [{'book': 46, 'ranges': [[9, 19, 9, 27]]},
                                  {'book': 42, 'ranges': [[3, 1, 3, 18]]}])
                easter = liturgy_refs(source, self.lines(source, '2026-04-12'))
                self.assertNotIn({'book': 43, 'ranges': [[20, 19, 20, 25]]}, easter)

    def test_other_services_cannot_become_an_unlabelled_pair(self):
        for source in ('ocu', 'ugcc'):
            pair = [line for line in self.lines(source, '2026-10-05') if line['refs']]
            for heading in ('Ран. –', 'Утр. —', 'Свята: Утр. —', 'Вечірня:', 'На вечірні:',
                            'На 1-му часі –', 'Царські часи', 'На осв. води:', 'На вмиванні:'):
                with self.subTest(source=source, heading=heading):
                    self.assertEqual(liturgy_refs(source, [{'text': heading, 'refs': []}] + pair), [])
                    lines = copy.deepcopy(pair)
                    lines[0]['text'] = heading + ' ' + lines[0]['text']
                    self.assertEqual(liturgy_refs(source, lines), [])
            # A lone Gospel or multiple pairs gives no implicit Liturgy evidence.
            self.assertEqual(liturgy_refs(source, pair + pair), [])
            self.assertEqual(liturgy_refs(source, [{'text': 'Єв. Лк.', 'refs': [pair[-1]['refs'][-1]]}]), [])
            self.assertEqual(liturgy_refs(source, self.lines(source, '2026-04-10')), [])


if __name__ == '__main__':
    unittest.main()
