"""Export Gospel verse timecodes from local cep_public without copying audio."""
from __future__ import annotations
import argparse
import datetime as dt
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sitegen.lectionary_data import SOURCE, load_json, encoded, require, walk_references
from sitegen.lectionary import Lectionary
from tools.build_gospel_today import extract_passage
from tools.build_reading_time import local_query, canonical_book

VOICES = {'ru': ('syn', 'prudovsky'), 'uk': ('ubh', 'kozlov_uk')}
TIMECODE_INPUT = SOURCE / 'timecodes.json'


def gospel_ids(items):
    result = []
    for item in items:
        if item.get('gospel'): result.append(item['gospel'])
        result.extend(item.get('gospel_composite', []))
        result.extend(h['gospel'] for h in item.get('hours', []))
    return result


def requirements(assets, start, end):
    needed = {lang: {} for lang in VOICES}
    for lang in VOICES:
        for year in range(start, end + 1):
            for date, day in assets[f'{lang}/{year}.json']['days'].items():
                for pid in gospel_ids(day['items']):
                    p = assets[f'{lang}/texts.json']['passages'][pid]
                    for verse in p['verses']:
                        key = f"{p['book']}:{verse['chapter']}:{verse['first']}"
                        needed[lang].setdefault(key, set()).add(date)
    return needed


def audit(needed, timing_rows):
    timings, issues = {}, []
    for voice, b, c, v, begin, end in timing_rows:
        key = (voice, f'{canonical_book(b)}:{c}:{v}')
        if key in timings:
            issues.append(f'duplicate timing: {key}')
        timings[key] = (begin, end)
    for lang, keys in needed.items():
        _, voice = VOICES[lang]
        for key, dates in sorted(keys.items()):
            value = timings.get((voice, key))
            if value is None:
                issues.append(f'{voice} {key}: missing timecode; days {", ".join(sorted(dates))}')
            elif not (all(type(t) in (int, float) and math.isfinite(t) for t in value)
                      and 0 <= value[0] < value[1]):
                issues.append(f'{voice} {key}: invalid timecode {value}; days {", ".join(sorted(dates))}')
    require(not issues, 'Gospel timecode coverage errors:\n' + '\n'.join(issues))
    return timings


def export_timecodes(start_year=2026, end_year=2030):
    require(type(start_year) is int and type(end_year) is int and 1901 <= start_year <= end_year <= 2098,
            'invalid timecode year range')
    # Export must not depend on an already valid generated bundle.
    lectionary = Lectionary(SOURCE / 'tables.json')
    snapshot = load_json(SOURCE / 'verses.json')
    needed = {lang: {} for lang in VOICES}
    passages = {}
    for lang, (translation, voice) in VOICES.items():
        date = dt.date(start_year, 1, 1)
        while date < dt.date(end_year + 1, 1, 1):
            for ref in walk_references(lectionary.day(date, 'julian' if lang == 'ru' else 'newjulian')['items']):
                if ref['book'] not in (40,41,42,43): continue
                identity = (lang, ref['book'], tuple(map(tuple,ref['ranges'])))
                if identity not in passages:
                    passages[identity] = extract_passage(ref, translation, snapshot['verses'][translation], lectionary.t['books'], lang)
                for verse in passages[identity]['verses']:
                    key = f"{ref['book']}:{verse['chapter']}:{verse['first']}"
                    needed[lang].setdefault(key,set()).add(date.isoformat())
            date += dt.timedelta(days=1)
    voices = local_query("SELECT JSON_ARRAY(v.alias,t.alias,v.is_music,v.active) FROM voices v JOIN translations t ON t.code=v.translation WHERE t.active=1 AND v.alias IN ('prudovsky','kozlov_uk')")
    require({tuple(v) for v in voices} == {('prudovsky','syn',0,1), ('kozlov_uk','ubh',0,1)}, 'requested narrators must be active, correct translation, no music')
    rows = local_query("SELECT JSON_ARRAY(v.alias,a.book_number,a.chapter_number,a.verse_number,a.begin,a.end) FROM voice_alignments a JOIN voices v ON v.code=a.voice WHERE v.alias IN ('prudovsky','kozlov_uk') ORDER BY v.alias,a.book_number,a.chapter_number,a.verse_number")
    timings = audit(needed, rows)
    data = {'schema_version': 1, 'exported_on': dt.datetime.now(dt.timezone.utc).date().isoformat(),
            'source': 'read-only local cep_public.voice_alignments',
            'voices': {lang: list(pair) for lang, pair in VOICES.items()},
            'timecodes': {lang: {key: list(timings[voice, key]) for key in sorted(needed[lang])}
                          for lang, (_, voice) in VOICES.items()}}
    TIMECODE_INPUT.write_bytes(encoded(data))
    print(f'Exported {sum(map(len, needed.values()))} verse timecodes; no audio files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-year', type=int, default=2026)
    parser.add_argument('--end-year', type=int, default=2030)
    args = parser.parse_args()
    export_timecodes(args.start_year, args.end_year)
