"""Export local read-only Scripture once; regenerate daily assets offline."""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sitegen.errors import BuildError
from sitegen.lectionary import Lectionary
from sitegen.lectionary_data import (SOURCE, BUNDLE_DIR, CALENDARS, TRANSLATIONS, load_json, encoded,
    digest, require, walk_references, passage_id, reference_key, validate_passages, validate_schedule)
from tools.build_reading_time import canonical_book, local_query


UBH_MATTHEW_23_14 = ('Горе вам, книжники та фарисеї, лицеміри, що проходите море й землю, '
                     'щоб придбати одного новонаверненого, і коли знайдете, то робите його '
                     'гідним пекла, подвійно від вас гіршим.')


def normalize_known_joins(verses):
    """Recognize the verified Khomenko 14–15 range flattened by bible.by.

    Evidence checked 2026-10-05:
    https://www.truechristianity.info/ua/biblia/matthew_ukr.php (explicit 14–15)
    https://bible.by/ubh/40/23/ (text at 14, empty 15)
    Unknown empty rows and changed neighbours are errors, not candidates for merging.
    """
    ubh = verses['ubh']
    first, empty = ubh.get('40:23:14'), ubh.get('40:23:15')
    if empty is None or empty['text'] != '':
        return []
    require(empty['last'] == 15 and first is not None and first['last'] in (14, 15)
            and first['text'] == UBH_MATTHEW_23_14, 'unrecognized UBH Matthew 23:14–15 representation')
    first['last'] = 15
    del ubh['40:23:15']
    return ['ubh-matthew23-14-15']


def export_local():
    # The public database already contains applied editorial fixes.
    rows = local_query("SELECT JSON_ARRAY(t.alias,v.book_number,v.chapter_number,v.verse_number,v.verse_number_join,v.text) FROM translation_verses v JOIN translations t ON t.code=v.translation WHERE t.active=1 AND t.alias IN ('syn','ubh') ORDER BY t.alias,v.book_number,v.chapter_number,v.verse_number")
    needed = {translation: set() for translation in TRANSLATIONS.values()}
    for ref in walk_references(load_json(SOURCE / 'tables.json')):
        for translation in needed:
            for c1, _, c2, _ in display_ranges(ref, translation):
                needed[translation].update((ref['book'], chapter) for chapter in range(c1, c2 + 1))
    verses = {translation: {} for translation in TRANSLATIONS.values()}
    for translation, b, c, first, join, text in rows:
        book = canonical_book(b)
        if (book, c) not in needed[translation]:
            continue
        require(isinstance(text, str), f'invalid local text: {translation}:{book}:{c}:{first}')
        if not text.strip():
            require((translation, book, c, first, join, text) == ('ubh', 40, 23, 15, 0, ''), f'empty local text: {translation}:{book}:{c}:{first}')
        require(type(join) is int and (join == 0 or join >= first), 'invalid joined verse')
        key = f'{book}:{c}:{first}'
        require(key not in verses[translation], f'duplicate local verse: {key}')
        verses[translation][key] = {'last': join if join else first, 'text': text}
    require(all(verses.values()), 'missing local translation')
    normalizations = normalize_known_joins(verses)
    snapshot = {'schema_version': 1, 'exported_on': dt.datetime.now(dt.timezone.utc).date().isoformat(),
                'source': 'read-only local cep_public in cep-mysql', 'normalizations': normalizations, 'verses': verses}
    (SOURCE / 'verses.json').write_bytes(encoded(snapshot))


def display_ranges(ref, translation):
    # Explicit versification difference, not a substitute for absent data.
    result = []
    for c1, v1, c2, v2 in ref['ranges']:
        if translation == 'ubh' and ref['book'] == 45 and c2 == 14 and v2 > 23:
            require(c1 == 14 and v2 <= 26, 'unhandled Romans doxology range')
            if v1 <= 23:
                result.append([14, v1, 14, 23])
            result.append([16, max(v1, 24) + 1, 16, v2 + 1])
        else:
            result.append([c1, v1, c2, v2])
    return result


def label(book, ranges, books, lang):
    spans = []
    for c1, v1, c2, v2 in ranges:
        end = str(v2) if c1 == c2 else f'{c2}:{v2}'
        spans.append(f'{c1}:{v1}' + (f'–{end}' if (c1, v1) != (c2, v2) else ''))
    return books[str(book)][lang + '_abbr'] + ' ' + '; '.join(spans)


def extract_passage(ref, translation, verses, books, lang):
    mapped = display_ranges(ref, translation)
    book = ref['book']
    result, seen = [], set()
    for c1, v1, c2, v2 in mapped:
        for chapter in range(c1, c2 + 1):
            available = {int(k.split(':')[2]): v for k, v in verses.items() if k.startswith(f'{book}:{chapter}:')}
            require(bool(available), f'missing chapter: {translation}:{book}:{chapter}')
            first, last = v1 if chapter == c1 else 1, v2 if chapter == c2 else max(v['last'] for v in available.values())
            require(first <= last, 'invalid chapter window')
            covered = set()
            for number, verse in sorted(available.items()):
                if number > last or verse['last'] < first:
                    continue
                require(isinstance(verse['text'], str) and bool(verse['text'].strip()), 'empty text')
                covered.update(range(max(first, number), min(last, verse['last']) + 1))
                coordinate = (chapter, number)
                if coordinate not in seen:
                    result.append({'chapter': chapter, 'first': number, 'last': verse['last'], 'text': verse['text']})
                    seen.add(coordinate)
            require(covered == set(range(first, last + 1)), f'missing verses: {translation}:{book}:{chapter}:{first}-{last}')
    return {'book': book, 'ranges': ref['ranges'], 'display_ranges': mapped,
            'label': label(book, mapped, books, lang), 'book_name': books[str(book)][lang], 'verses': result}


def primary(day):
    for item in day['items']:
        if item.get('gospel'):
            return item['gospel']
        if item.get('gospel_composite'):
            return item['gospel_composite'][0]
        if item.get('hours'):
            return item['hours'][0]['gospel']
    for item in day['items']:
        if item.get('ot'):
            return item['ot'][0]
    raise BuildError(f'no primary reading: {day}')


def accuracy(lectionary, references):
    result = {}
    for source in ('azbyka_roc', 'pravoslavie_roc', 'ocu', 'ugcc'):
        days = {day['date']: {reference_key(r) for r in day['refs']} for day in references[source]}
        counts = {'exact': 0, 'adjacent': 0, 'mismatch': 0, 'no_source': 0}
        for date, have in days.items():
            if not have:
                counts['no_source'] += 1
                continue
            x = dt.date.fromisoformat(date)
            key = reference_key(primary(lectionary.day(x, 'newjulian' if source in ('ocu', 'ugcc') else 'julian')))
            near = set().union(*(days.get((x + dt.timedelta(days=n)).isoformat(), set()) for n in (-1, 1)))
            counts['exact' if key in have else 'adjacent' if key in near else 'mismatch'] += 1
        counts['denominator'] = counts['exact'] + counts['adjacent'] + counts['mismatch']
        result[source] = counts
    return result


def compact_day(day, lang, references):
    def compact(value):
        if isinstance(value, dict):
            if 'book' in value and 'ranges' in value:
                return passage_id(value)
            return {k: (v[lang] if k == 'name' else compact(v)) for k, v in value.items()
                    if k not in {'date', 'calendar', 'week', 'rank', 'key', 'apostle_key', 'gospel_key'}}
        if isinstance(value, list):
            return [compact(v) for v in value]
        return value
    out = compact(day)
    out['confirmed_by'] = []
    if lang == 'uk':
        needed = {reference_key(r) for r in walk_references(day['items'])}
        for source in ('ocu', 'ugcc'):
            evidence = references[source].get(day['date'], set())
            if needed and needed <= evidence:
                out['confirmed_by'].append(source)
        out['uncertain'] = not bool(out['confirmed_by'])
    else:
        out['uncertain'] = 'uncertain' in day
    return out


def generate(start_year=2026, end_year=2030):
    require(type(start_year) is int and type(end_year) is int and 1901 <= start_year <= end_year <= 2098, 'invalid generation range')
    L = Lectionary(SOURCE / 'tables.json')
    snapshot = load_json(SOURCE / 'verses.json')
    require(set(snapshot) == {'schema_version', 'exported_on', 'source', 'normalizations', 'verses'} and type(snapshot['schema_version']) is int and snapshot['schema_version'] == 1, 'invalid verse snapshot')
    require(snapshot['normalizations'] in ([], ['ubh-matthew23-14-15']), 'unknown snapshot normalization')
    require(set(snapshot['verses']) == set(TRANSLATIONS.values()), 'missing translation snapshot')
    refs = load_json(SOURCE / 'references.json')
    evidence = {source: {d['date']: {reference_key(r) for r in d['liturgy_refs']} for d in refs[source]} for source in ('ocu', 'ugcc')}
    files = {}
    for lang, calendar in CALENDARS.items():
        passages, schedules = {}, {}
        for year in range(start_year, end_year + 1):
            days = {}
            x, end = dt.date(year, 1, 1), dt.date(year + 1, 1, 1)
            while x < end:
                day = L.day(x, calendar)
                for ref in walk_references(day['items']):
                    pid = passage_id(ref)
                    if pid not in passages:
                        passages[pid] = extract_passage(ref, TRANSLATIONS[lang], snapshot['verses'][TRANSLATIONS[lang]], L.t['books'], lang)
                days[x.isoformat()] = compact_day(day, lang, evidence)
                x += dt.timedelta(days=1)
            schedules[year] = {'schema_version': 1, 'calendar': calendar, 'year': year, 'days': days}
        texts = {'schema_version': 1, 'translation': TRANSLATIONS[lang], 'passages': passages}
        validate_passages(texts, lang)
        files[f'{lang}/texts.json'] = encoded(texts)
        for year, schedule in schedules.items():
            validate_schedule(schedule, lang, year, passages)
            files[f'{lang}/{year}.json'] = encoded(schedule)
    manifest = {'schema_version': 1, 'start_year': start_year, 'end_year': end_year,
                'files': {name: digest(payload) for name, payload in files.items()},
                'inputs': {name: digest((SOURCE / name).read_bytes()) for name in ('tables.json', 'references.json', 'verses.json')}}
    files['manifest.json'] = encoded(manifest)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-year', type=int, default=2026)
    parser.add_argument('--end-year', type=int, default=2030)
    parser.add_argument('--export-local', action='store_true')
    args = parser.parse_args()
    if args.export_local:
        export_local()
    files = generate(args.start_year, args.end_year)
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    for name, payload in files.items():
        path = BUNDLE_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f'Generated {len(files)} files, {sum(map(len, files.values()))} bytes')


if __name__ == '__main__':
    main()
