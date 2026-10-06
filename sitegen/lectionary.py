"""Table-driven Orthodox daily readings; source provenance is in tools/data/lectionary."""
from .errors import BuildError
from .lectionary_data import load_json, validate_tables

import datetime as dt

D, TD = dt.date, dt.timedelta
WD = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


def pascha(year):
    if type(year) is not int or not 1900 <= year <= 2099:
        raise BuildError("Paschalion requires a year in 1900..2099")
    """Orthodox Pascha: Julian computus (Meeus), converted to the civil Gregorian date (valid 1900..2099)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return D(year, month, day) + TD(days=13)


def count_week(p0, x):
    """Week after Pentecost: Monday after Pentecost opens week 1; Sunday k (Sunday after Pentecost no. k) closes week k."""
    return ((x - p0).days - 50) // 7 + 1


class Cycle:
    """One paschal year [P0, P1)."""

    def __init__(self, p0, calendar, winter):
        if calendar not in ("julian", "newjulian"):
            raise BuildError(f"unknown calendar: {calendar}")
        self.winter = winter
        self.p0, self.p1, self.calendar = p0, pascha(p0.year + 1), calendar
        self.shift = 13 if calendar == 'julian' else 0
        self.publican = self.p1 - TD(days=70)
        self.K = count_week(p0, self.publican)          # weekdays of week K (before Publican Sunday) read week 33
        self.sun_after_exaltation = self.sunday_in(p0.year, 9, 15, 21)
        self.luke_start = self.sun_after_exaltation + TD(days=1)
        self.wL = count_week(p0, self.luke_start)
        self.forefathers = self.sunday_in(p0.year, 12, 11, 17)
        self.G = self._gospel_weeks()

    def civil(self, y, m, d):
        return D(y, m, d) + TD(days=self.shift)

    def church_md(self, x):
        c = x - TD(days=self.shift)
        return c.month, c.day

    def sunday_in(self, y, m, d1, d2):
        for d in range(d1, d2 + 1):
            x = self.civil(y, m, d)
            if x.weekday() == 6:
                return x
        raise BuildError("missing Sunday in feast window")

    def _gospel_weeks(self):
        """Gospel week read in each count-week 1..K (weekdays, Saturday and Sunday of that week)."""
        G = {}
        if self.calendar == 'julian':
            for k in range(1, self.wL):
                if k <= 17:
                    G[k] = k
                else:  # early Pascha, Luke not started yet: repeat week 11 (weeks 10-11 if two are needed) — MP practice
                    need = self.wL - 18
                    G[k] = 11 - need + (k - 17)
            k = self.wL
            while 18 + (k - self.wL) <= 33 and k <= self.K:
                G[k] = 18 + (k - self.wL)
                k += 1
            k33 = max(G)
            self.k33 = k33
            for j, w in enumerate(winter_sequence(self.K - k33, self.winter), start=1):   # winter (Theophany) 'отступка'
                G[k33 + j] = w
            self.gap_weeks = set()
            return G
        # newjulian (OCU Богослужбові вказівки 2026): sequential weeks; the two weeks before Publican Sunday read
        # weeks 32 and 33; weeks in between are filled from week 29 on (observed for one gap week only).
        for k in range(1, self.K + 1):
            G[k] = k
        self.gap_weeks = set()
        if self.K > 33:
            fill = [29, 30, 31, 17, 16]
            for j, k in enumerate(range(32, self.K - 1)):
                G[k] = fill[j]
                self.gap_weeks.add(k)
            G[self.K - 1], G[self.K] = 32, 33
        self.k33 = 31 if self.K > 33 else self.K    # weeks after k33 read Apostle and Gospel of the same (repeated) week
        return G


def winter_sequence(r, winter):
    if str(r) not in winter:
        raise BuildError(f"missing winter sequence: {r}")
    return winter[str(r)]


VERIFIED_WINTER = {2, 3, 4, 5}


class Lectionary:
    def __init__(self, tables_path):
        t = load_json(tables_path)
        validate_tables(t)
        self.t = t
        self.fixed = {(f['month'], f['day']): f for f in t['fixed']}

    def reading(self, key):
        if key not in self.t['readings']:
            raise BuildError(f'missing reading: {key}')
        return self.t['readings'][key]

    def ordinary(self, c, x):
        """(apostle_key, gospel_key) of the ordinary readings, keys into tables['readings']."""
        k = count_week(c.p0, x)
        wd = WD[x.weekday()]
        if k not in c.G:
            raise BuildError(f"missing gospel week: {k}")
        g = c.G[k]
        winter = k > c.k33
        a = g if winter else k
        if wd != 'sun':
            if g is None:
                return None, None
            return f'pent{a}.{wd}', f'pent{g}.{wd}'
        # Sundays
        if x == c.forefathers:          # Typikon, Dec 11: Apostle of Sunday 29, Gospel of Sunday 28
            return 'pentsun29', 'pentsun28'
        if k == c.K - 1:                # Sunday before Publican: always Zacchaeus (Sunday 32)
            return 'pentsun32', 'pentsun32'
        if g in (32, 33):
            g = None
        if a is not None and a > 31 and not winter:
            a = None
        ff = c.forefathers
        kff = count_week(c.p0, ff)
        gff = c.G.get(kff)
        aff = kff if kff <= c.k33 else gff
        gkey = f'pentsun{g}' if g else None
        akey = f'pentsun{a}' if a else None
        if g == 28:                     # swap with Forefathers
            gkey = f'pentsun{gff}' if gff else None
        if a == 29 and not winter:
            akey = f'pentsun{aff}'
        return akey, gkey

    def special_for(self, c, x):
        md = c.church_md(x)
        wd = WD[x.weekday()]
        for s in self.t['special']:
            if s['weekday'] != wd:
                continue
            f, t = tuple(s['from']), tuple(s['to'])
            inside = (f <= md <= t) if f <= t else (md >= f or md <= t)
            if inside:
                return s
        return None

    def day(self, x, calendar='julian'):
        if not isinstance(x, dt.date) or not 1901 <= x.year <= 2098:
            raise BuildError('daily calculation requires a date in 1901..2098')
        p = pascha(x.year)
        c = Cycle(p if x >= p else pascha(x.year - 1), calendar, self.t['winter_sequences'])
        o, to_next = (x - c.p0).days, (x - c.p1).days
        wd = WD[x.weekday()]
        out = {'date': x.isoformat(), 'calendar': calendar, 'items': []}
        items = out['items']
        md = c.church_md(x)
        feast = self.fixed.get(md)
        # Royal Hours on the Friday before an Eve that falls on Saturday/Sunday: no Liturgy that day
        for eve_md, which in (((12, 24), 'nativity'), ((1, 5), 'theophany')):
            for y in (x.year - 1, x.year, x.year + 1):
                eve = c.civil(y, *eve_md)
                if wd == 'fri' and eve.weekday() in (5, 6) and 0 < (eve - x).days <= 2:
                    out['period'] = 'royal_hours'
                    out['items'].append({'kind': 'royal_hours', 'id': which, 'hours': self.t['royal_hours'][which]})
                    return out
        if feast and feast['id'] == 'nativity_eve' and wd == 'sun':
            feast = None                # Sunday Eve: only the Sunday before Nativity (Holy Fathers); pravoslavie.ru 2019-01-06
        elif feast and feast['id'] == 'nativity_eve' and wd == 'sat':
            v = self.t['fixed_variants']['nativity_eve_weekend']
            feast = dict(feast, apostle=v['apostle'], gospel=v['gospel'], rank='eve_weekend')
        elif feast and feast['id'] == 'theophany_eve' and wd in ('sat', 'sun'):
            feast = None                # Liturgy of the Saturday/Sunday before Theophany; Vespers served separately
        movable = []
        if to_next >= -70:
            out['period'] = 'triodion'
            movable.append(('triodion', f'trio{to_next}'))
        elif o <= 49:
            out['period'] = 'pentecostarion'
            movable.append(('pentecostarion', f'pasch{o}'))
        else:
            out['period'] = 'ordinary'
            out['week'] = count_week(c.p0, x)
            w = out['week']
            if w in c.gap_weeks or (calendar == 'julian' and w > c.k33 and (c.K - c.k33) not in VERIFIED_WINTER):
                out['uncertain'] = 'winter_otstupka'   # order of repeated weeks not confirmed by a published calendar
            if calendar == 'julian' and c.church_md(x) in ((1, 2), (1, 3), (1, 4)) and wd not in ('sat', 'sun'):
                out['note'] = 'ordinary_may_be_omitted'   # MP practice: forefeast of Theophany, "ввиду Крещенской отступки"
        if feast:
            items.append({'kind': 'feast', 'id': feast['id'], 'rank': feast['rank'], 'name': feast['name'],
                          'apostle': feast['apostle'], 'gospel': feast['gospel']})
            lord = feast['rank'] == 'lord'
            # Lord's feasts replace everything; other great feasts replace weekday ordinary readings
            if lord or feast['rank'] in ('eve', 'eve_weekend') and wd != 'sun' or (wd != 'sun' and out['period'] == 'ordinary'):
                return out
        if out['period'] == 'ordinary':
            sp = self.special_for(c, x)
            a, g = self.ordinary(c, x)
            if sp:
                spi = {'kind': 'special', 'id': sp['id'], 'name': sp['name'],
                       'apostle': sp['apostle'], 'gospel': sp['gospel']}
                if sp['ordinary'] == 'before':
                    self._add_ordinary(items, a, g)
                    items.append(spi)
                else:
                    items.append(spi)
                    if sp['ordinary'] == 'under':
                        self._add_ordinary(items, a, g)
            else:
                self._add_ordinary(items, a, g)
        else:
            for kind, key in movable:
                r = self.reading(key)
                if r:
                    it = {'kind': kind, 'key': key, 'apostle': r.get('apostle'), 'gospel': r.get('gospel')}
                    for extra in ('ot', 'gospel_composite', 'note'):
                        if r.get(extra):
                            it[extra] = r[extra]
                    items.append(it)
        if not items:
            raise BuildError(f'{x}: no readings calculated')
        return out

    def _add_ordinary(self, items, akey, gkey):
        ra = self.reading(akey) if akey else None
        rg = self.reading(gkey) if gkey else None
        a = ra.get('apostle') if ra else None
        g = rg.get('gospel') if rg else None
        if a or g:
            items.append({'kind': 'ordinary', 'apostle_key': akey, 'gospel_key': gkey, 'apostle': a, 'gospel': g})
