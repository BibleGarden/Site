"""Paschalion, lectionary rules and dated reference thresholds."""
import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from sitegen.errors import BuildError
from sitegen.lectionary import Lectionary, pascha, winter_sequence
from sitegen.lectionary_data import SOURCE, load_json, validate_tables
from tools.build_gospel_today import accuracy, compact_day


class LectionaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = Lectionary(SOURCE / 'tables.json')

    def test_paschalion(self):
        for year, expected in [(2024, '2024-05-05'), (2025, '2025-04-20'), (2026, '2026-04-12'),
                               (2027, '2027-05-02'), (2028, '2028-04-16'), (2029, '2029-04-08'), (2030, '2030-04-28')]:
            self.assertEqual(pascha(year).isoformat(), expected)
        for year in (1899, 2100, True, '2026'):
            with self.assertRaises(BuildError): pascha(year)
        with self.assertRaises(BuildError): self.L.day(dt.date(1900, 1, 1))
        with self.assertRaises(BuildError): self.L.day(dt.date(2026, 1, 1), 'gregorian')
        with self.assertRaises(BuildError): winter_sequence(6, self.L.t['winter_sequences'])

    def pair(self, date, calendar='julian', index=0):
        item = self.L.day(dt.date.fromisoformat(date), calendar)['items'][index]
        return tuple(item[k]['ref'] if item.get(k) else None for k in ('apostle', 'gospel'))

    def test_known_days(self):
        cases = [
            ('2026-10-05', 'Флп. 1:1–7', 'Лк. 3:19–22'),
            ('2026-09-28', 'Еф. 4:25–32', 'Мф. 23:13–22'),
            ('2024-09-30', 'Гал. 2:11–16', 'Лк. 3:19–22'),
            ('2024-12-29', 'Кол. 3:4–11', 'Лк. 14:16–24'),
            ('2024-12-15', 'Еф. 4:1–6', 'Лк. 18:18–27'),
            ('2025-01-07', 'Гал. 4:4–7', 'Мф. 2:1–12'),
            ('2024-01-06', 'Гал. 3:15–22', 'Мф. 13:31–36'),
            ('2026-01-25', 'Еф. 4:7–13', 'Мф. 4:12–17'),
            ('2026-01-26', '1Пет. 2:21–3:9', 'Мк. 12:13–17'),
            ('2024-02-05', 'Еф. 1:22–2:3', 'Мк. 10:46–52'),
            ('2024-02-11', '2Кор. 6:16–7:1', 'Мф. 15:21–28'),
            ('2026-04-12', 'Деян. 1:1–8', 'Ин. 1:1–17'),
            ('2026-05-21', 'Деян. 1:1–12', 'Лк. 24:36–53'),
        ]
        for date, apostle, gospel in cases:
            with self.subTest(date=date): self.assertEqual(self.pair(date), (apostle, gospel))
        self.assertEqual(self.pair('2026-01-25', index=1), ('1Тим. 4:9–15', 'Лк. 19:1–10'))
        for date, apostle, gospel in [
            ('2026-10-05', 'Флп. 1:1–7', 'Лк. 4:37–44'),
            ('2026-09-28', 'Еф. 4:25–32', 'Лк. 3:19–22'),
            ('2026-12-25', 'Гал. 4:4–7', 'Мф. 2:1–12'),
            ('2026-01-12', 'Евр. 3:5–11, 17–19', 'Лк. 20:27–44'),
            ('2026-01-25', '1Тим. 4:9–15', 'Лк. 19:1–10'),
        ]:
            with self.subTest(date=date): self.assertEqual(self.pair(date, 'newjulian'), (apostle, gospel))

    def test_lent_composite_and_hours(self):
        lent = self.L.day(dt.date(2026, 3, 4))['items'][0]
        self.assertIsNone(lent['gospel'])
        self.assertEqual([r['ref'] for r in lent['ot']], ['Ис. 5:16–25', 'Быт. 4:16–26', 'Притч. 5:15–6:3'])
        self.assertTrue(self.L.day(dt.date(2026, 4, 10))['items'][0]['gospel_composite'])
        hours = self.L.day(dt.date(2024, 1, 5))
        self.assertEqual(hours['period'], 'royal_hours')
        self.assertEqual([h['hour'] for h in hours['items'][0]['hours']], [1, 3, 6, 9])
        self.assertEqual(len(self.L.day(dt.date(2025, 1, 7))['items']), 1)
        for date in ('2028-04-07', '2030-04-07'):
            self.assertTrue(self.L.day(dt.date.fromisoformat(date))['items'])

    def test_reference_thresholds_and_fixed_denominators(self):
        measured = accuracy(self.L, load_json(SOURCE / 'references.json'))
        for source, numerator, denominator, threshold in [
            ('azbyka_roc', 993, 1042, .95), ('pravoslavie_roc', 1056, 1133, .93),
            ('ocu', 302, 331, .91), ('ugcc', 617, 669, .92),
        ]:
            self.assertEqual((measured[source]['exact'], measured[source]['denominator']), (numerator, denominator))
            self.assertGreaterEqual(numerator / denominator, threshold)
        self.assertGreaterEqual((measured['azbyka_roc']['exact'] + measured['azbyka_roc']['adjacent']) / 1042, .99)

    def test_missing_tables_and_references_fail(self):
        t = copy.deepcopy(self.L.t)
        del t['readings']['pasch0']
        with self.assertRaises(BuildError): validate_tables(t)
        with self.assertRaises(BuildError): self.L.reading('unknown')
        t = copy.deepcopy(self.L.t)
        t['readings']['pasch0']['gospel']['ranges'][0][1] = 0
        with self.assertRaises(BuildError): validate_tables(t)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'x.json'; path.write_text('{"a":1,"a":2}')
            with self.assertRaises(BuildError): load_json(path)

    def test_uncertainty_requires_all_readings_and_same_date(self):
        day = self.L.day(dt.date(2026, 10, 5), 'newjulian')
        self.assertTrue(compact_day(day, 'uk', {'ocu': {}, 'ugcc': {}})['uncertain'])
        from sitegen.lectionary_data import reference_key, walk_references
        all_refs = {reference_key(r) for r in walk_references(day['items'])}
        evidence = {'ocu': {day['date']: all_refs}, 'ugcc': {}}
        self.assertFalse(compact_day(day, 'uk', evidence)['uncertain'])
        evidence['ocu'][day['date']].pop()
        self.assertTrue(compact_day(day, 'uk', evidence)['uncertain'])
