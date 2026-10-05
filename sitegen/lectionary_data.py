"""Strict shared validation for committed lectionary inputs and public passages."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from .errors import BuildError
from .reading_plan import CHAPTER_COUNTS

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'tools/data/lectionary'
BUNDLE_DIR = ROOT / 'content/bible-garden/lectionary'
CALENDARS = {'ru': 'julian', 'uk': 'newjulian'}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def reject_constant(value):
    raise BuildError(f"invalid JSON constant: {value}")


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_keys, parse_constant=reject_constant)
    except (OSError, ValueError) as error:
        raise BuildError(f'{path}: {error}') from error


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def require(condition, message):
    if not condition:
        raise BuildError(f'lectionary: {message}')


def reference_key(ref):
    return (ref['book'], tuple(tuple(r) for r in ref['ranges']))


def passage_id(ref):
    return 'p-' + digest(encoded({'book': ref['book'], 'ranges': ref['ranges']}))[:16]


def validate_reference(ref):
    require(isinstance(ref, dict) and {'book', 'ranges'} <= ref.keys(), 'invalid reference')
    book = ref['book']
    require(type(book) is int and 1 <= book <= 66, 'invalid book')
    require(isinstance(ref['ranges'], list) and bool(ref['ranges']), 'empty ranges')
    for span in ref['ranges']:
        require(isinstance(span, list) and len(span) == 4 and all(type(v) is int and v > 0 for v in span), 'invalid range')
        c1, v1, c2, v2 = span
        require((c1, v1) <= (c2, v2) and c2 <= CHAPTER_COUNTS[book - 1], 'reversed or invalid range')


def walk_references(value):
    if isinstance(value, dict):
        if 'book' in value and 'ranges' in value:
            validate_reference(value)
            yield value
        else:
            for item in value.values():
                yield from walk_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_references(item)


def validate_tables(tables):
    require(isinstance(tables, dict) and set(tables) == {'meta', 'books', 'readings', 'fixed', 'fixed_variants', 'special', 'royal_hours', 'winter_sequences'}, 'invalid tables schema')
    expected = {f'pasch{i}' for i in range(50)} | {f'trio{i}' for i in range(-70, 0)}
    expected |= {f'pent{k}.{w}' for k in range(1, 34) for w in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat')}
    expected |= {f'pentsun{k}' for k in range(1, 33)}
    # Some source tables also contain explicitly identified Sunday alternatives.
    require(expected <= tables['readings'].keys(), f'missing reading tables: {sorted(expected - tables["readings"].keys())}')
    require(set(tables['winter_sequences']) == {str(i) for i in range(6)}, 'missing winter sequences')
    for r, weeks in tables['winter_sequences'].items():
        require(len(weeks) == int(r) and all(type(k) is int and 1 <= k <= 33 for k in weeks), 'invalid winter sequence')
    for book in tables['books'].values():
        for lang in CALENDARS:
            require(all(isinstance(book[k], str) and book[k].strip() for k in (lang, lang + '_abbr')), 'missing book label')
    list(walk_references(tables))
    for entry in tables['readings'].values():
        require({'apostle', 'gospel'} <= entry.keys(), 'reading must explicitly declare Apostle and Gospel')
        require(entry['apostle'] is not None or entry['gospel'] is not None or bool(entry.get('ot')) or bool(entry.get('gospel_composite')), 'empty reading')
    require(len({(entry['month'], entry['day']) for entry in tables['fixed']}) == len(tables['fixed']), 'duplicate fixed feast')
    for entry in tables['fixed']:
        require(entry['rank'] in {'lord', 'theotokos', 'theotokos_minor', 'great', 'eve'}, 'unknown feast rank')
        try:
            dt.date(2024, entry['month'], entry['day'])
        except (ValueError, TypeError) as error:
            raise BuildError('invalid fixed feast date') from error
    for entry in tables['special']:
        require(entry['weekday'] in {'sat', 'sun'} and entry['ordinary'] in {'under', 'before', 'none'}, 'invalid special reading rule')
    for entry in tables['fixed'] + tables['special']:
        require(all(isinstance(entry['name'][lang], str) and entry['name'][lang].strip() for lang in CALENDARS), 'missing feast label')


def validate_passages(data, lang):
    from .gospel_audio import EDITIONS, UNAVAILABLE, validate_audio
    require(set(data) == {'schema_version', 'translation', 'passages'} and type(data['schema_version']) is int and data['schema_version'] == 2
            and data['translation'] in EDITIONS and EDITIONS[data['translation']]['language'] == lang, 'invalid passage schema')
    require(isinstance(data['passages'], dict) and bool(data['passages']), 'empty passages')
    for pid, passage in data['passages'].items():
        if 'unavailable' in passage:
            require(set(passage) == {'book', 'ranges', 'label', 'book_name', 'unavailable'} and passage['unavailable'] in UNAVAILABLE, 'invalid unavailable passage')
            require(all(isinstance(passage[k],str) and passage[k].strip() for k in ('label','book_name')), 'invalid unavailable reference')
            validate_reference(passage)
            require(pid == passage_id(passage), 'invalid unavailable passage id')
            continue
        require(set(passage) == {'book', 'ranges', 'display_ranges', 'label', 'book_name', 'verses', 'audio'}, 'invalid passage fields')
        validate_reference(passage)
        require(pid == passage_id(passage), 'invalid passage id')
        require(isinstance(passage['book_name'], str) and bool(passage['book_name'].strip()), 'empty book name')
        require(isinstance(passage['label'], str) and bool(passage['label'].strip()), 'empty passage label')
        require(isinstance(passage['verses'], list) and bool(passage['verses']), 'empty passage text')
        seen = set()
        for verse in passage['verses']:
            require(set(verse) == {'chapter', 'first', 'last', 'text'}, 'invalid verse fields')
            require(all(type(verse[k]) is int and verse[k] > 0 for k in ('chapter', 'first', 'last')) and verse['first'] <= verse['last'], 'invalid verse coordinate')
            require(isinstance(verse['text'], str) and bool(verse['text'].strip()), 'empty verse text')
            coordinate = (verse['chapter'], verse['first'], verse['last'])
            require(coordinate not in seen, 'duplicate passage verse')
            seen.add(coordinate)
        validate_audio(passage, data['translation'])
        validate_reference({'book': passage['book'], 'ranges': passage['display_ranges']})
        for c1, v1, c2, v2 in passage['display_ranges']:
            for chapter in range(c1, c2 + 1):
                available = {number for verse in passage['verses'] if verse['chapter'] == chapter for number in range(verse['first'], verse['last'] + 1)}
                require(bool(available), 'missing passage chapter')
                first, last = v1 if chapter == c1 else 1, v2 if chapter == c2 else max(available)
                require(set(range(first, last + 1)) <= available, 'missing interior verse')
            require(any(v['chapter'] == c1 and v['first'] <= v1 <= v['last'] for v in passage['verses']), 'missing first verse')
            require(any(v['chapter'] == c2 and v['first'] <= v2 <= v['last'] for v in passage['verses']), 'missing last verse')

def validate_schedule(data, lang, year, passages):
    require(set(data) == {'schema_version', 'calendar', 'year', 'days'} and type(data['schema_version']) is int and data['schema_version'] == 1 and data['calendar'] == CALENDARS[lang] and data['year'] == year, 'invalid schedule schema')
    first, end = dt.date(year, 1, 1), dt.date(year + 1, 1, 1)
    require(set(data['days']) == {(first + dt.timedelta(days=i)).isoformat() for i in range((end - first).days)}, 'missing or extra days')
    validate_days(data['days'], lang, passages)


def validate_days(days, lang, passages):
    def ref(pid):
        require(isinstance(pid, str) and pid in passages, f'missing passage: {pid}')
    for day in days.values():
        require(set(day) <= {'period', 'items', 'uncertain', 'confirmed_by', 'note'} and {'period', 'items', 'uncertain', 'confirmed_by'} <= day.keys(), 'invalid day fields')
        require(day['period'] in {'ordinary', 'triodion', 'pentecostarion', 'royal_hours'}, 'invalid period')
        if 'note' in day:
            require(day['note'] == 'ordinary_may_be_omitted', 'unknown daily note')
        require(type(day['uncertain']) is bool and isinstance(day['confirmed_by'], list) and set(day['confirmed_by']) <= {'ocu', 'ugcc'}, 'invalid verification')
        require(lang != 'uk' or day['uncertain'] or bool(day['confirmed_by']), 'unconfirmed Ukrainian date')
        require(isinstance(day['items'], list) and bool(day['items']), 'empty day')
        for item in day['items']:
            require(item['kind'] in {'ordinary', 'feast', 'special', 'triodion', 'pentecostarion', 'royal_hours'}, 'invalid reading kind')
            require(set(item) <= {'kind', 'id', 'name', 'apostle', 'gospel', 'ot', 'gospel_composite', 'note', 'hours'}, 'invalid item fields')
            if 'name' in item:
                require(isinstance(item['name'], str) and bool(item['name'].strip()), 'empty reading name')
            if 'note' in item:
                require(item['note'] in {'no_liturgy', 'no_liturgy_gospel', 'no_liturgy_vespers_gospel', 'presanctified'}, 'unknown reading note')
            refs = []
            for k in ('apostle', 'gospel'):
                if k in item and item[k] is not None: refs.append(item[k])
            for k in ('ot', 'gospel_composite'):
                if k in item:
                    require(isinstance(item[k], list) and bool(item[k]), 'empty reading list')
                    refs.extend(item[k])
            if 'hours' in item:
                require(len(item['hours']) == 4, 'expected four Royal Hours')
                for hour in item['hours']:
                    require(set(hour) == {'hour', 'apostle', 'gospel'} and hour['hour'] in (1, 3, 6, 9), 'invalid Royal Hour')
                    refs.extend((hour['apostle'], hour['gospel']))
            require(bool(refs), 'empty reading item')
            for pid in refs: ref(pid)


def load_bundle(directory=BUNDLE_DIR):
    from .gospel_audio import EDITIONS
    directory = Path(directory)
    manifest = load_json(directory / 'manifest.json')
    require(set(manifest) == {'schema_version', 'start_year', 'end_year', 'files', 'inputs'}, 'invalid manifest')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 2 and type(manifest['start_year']) is int and type(manifest['end_year']) is int and 1901 <= manifest['start_year'] <= manifest['end_year'] <= 2098, 'invalid year range')
    expected = {f'{t}/texts.json' for t in EDITIONS} | {f'{lang}/{year}.json' for lang in CALENDARS for year in range(manifest['start_year'], manifest['end_year'] + 1)}
    require(set(manifest['files']) == expected, 'invalid manifest files')
    require({str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()} == expected | {'manifest.json'}, 'missing or extra source bundle files')
    require(set(manifest['inputs']) == {'tables.json', 'references.json', 'verses.json', 'timecodes.json', 'book-names.json'}, 'invalid source fingerprints')
    for name, checksum in manifest['inputs'].items():
        require(digest((SOURCE / name).read_bytes()) == checksum, f'changed source input: {name}; regenerate')
    data = {}
    for name in sorted(expected):
        require(digest((directory / name).read_bytes()) == manifest['files'][name], f'checksum mismatch: {name}')
        data[name] = load_json(directory / name)
    for translation, edition in EDITIONS.items():
        validate_passages(data[f'{translation}/texts.json'], edition['language'])
    for lang in CALENDARS:
        for year in range(manifest['start_year'], manifest['end_year'] + 1):
            validate_schedule(data[f'{lang}/{year}.json'], lang, year, data['syn/texts.json']['passages'])
    return manifest, data


def referenced_passages(days):
    """All passages needed by daily, OT, composite and Hours readings."""
    refs = set()
    for day in days.values():
        for item in day['items']:
            refs.update(item[k] for k in ('apostle', 'gospel') if item.get(k) is not None)
            for key in ('ot', 'gospel_composite'):
                if key in item:
                    refs.update(item[key])
            if 'hours' in item:
                for hour in item['hours']:
                    refs.update((hour['apostle'], hour['gospel']))
    return refs


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



def validate_month(data, lang, year, month):
    require(isinstance(data,dict) and set(data) == {'schema_version','calendar','year','month','days','references'}, 'invalid monthly schedule')
    require(type(data['schema_version']) is int and data['schema_version']==3 and data['calendar']==CALENDARS[lang]
            and type(data['year']) is int and data['year']==year and type(data['month']) is int and data['month']==month
            and isinstance(data['days'],dict), 'invalid monthly metadata')
    first = dt.date(year,month,1)
    end = dt.date(year+1,1,1) if month==12 else dt.date(year,month+1,1)
    require(set(data['days']) == {(first+dt.timedelta(days=i)).isoformat() for i in range((end-first).days)}, 'missing or extra monthly days')
    require(isinstance(data['references'],dict) and set(data['references'])==referenced_passages(data['days']), 'missing or unused monthly references')
    for pid, ref in data['references'].items():
        require(set(ref)=={'book','ranges'} and pid==passage_id(ref), 'invalid monthly reference')
        validate_reference(ref)
    validate_days(data['days'],lang,data['references'])


def validate_chapter(data, translation, book, chapter):
    from .gospel_audio import EDITIONS, UNAVAILABLE, valid_timing
    require(isinstance(data,dict) and set(data)=={'schema_version','translation','book','chapter','book_name','abbr','unavailable','verses','audio'}, 'invalid chapter schema')
    require(type(data['schema_version']) is int and data['schema_version']==3 and data['translation']==translation
            and translation in EDITIONS and type(data['book']) is int and data['book']==book and 1<=book<=66
            and type(data['chapter']) is int and data['chapter']==chapter and chapter>0, 'invalid chapter identity')
    require(all(isinstance(data[k],str) and data[k].strip() for k in ('book_name','abbr')), 'invalid chapter labels')
    require(data['unavailable'] is None or data['unavailable'] in UNAVAILABLE, 'invalid unavailable chapter')
    require(isinstance(data['verses'],list) and isinstance(data['audio'],dict)
            and set(data['audio'])==set(EDITIONS[translation]['voices']), 'invalid chapter voices')
    require(bool(data['verses']) == (data['unavailable'] is None), 'invalid chapter availability')
    previous = 0
    for verse in data['verses']:
        require(isinstance(verse,list) and len(verse)==3 and all(type(v) is int and v>0 for v in verse[:2])
                and previous<verse[0]<=verse[1] and isinstance(verse[2],str) and verse[2].strip(), 'invalid chapter verse')
        previous=verse[0]
    for segments in data['audio'].values():
        require(isinstance(segments,list) and len(segments)==len(data['verses']), 'invalid chapter alignment count')
        for segment in segments:
            require(segment is None or (isinstance(segment,list) and len(segment)==2 and valid_timing(*segment)), 'invalid chapter timing')


def public_files(manifest, assets):
    """Monthly references plus each required translated chapter exactly once."""
    from .gospel_audio import EDITIONS
    verse_snapshot=load_json(SOURCE/'verses.json')
    timings=load_json(SOURCE/'timecodes.json')['timecodes']
    books=load_json(SOURCE/'book-names.json')
    files, references = {}, {}
    source=assets['syn/texts.json']['passages']
    for lang in CALENDARS:
        for year in range(manifest['start_year'],manifest['end_year']+1):
            annual=assets[f'{lang}/{year}.json']['days']
            for month in range(1,13):
                days={date:day for date,day in annual.items() if int(date[5:7])==month}
                refs={pid:{'book':source[pid]['book'],'ranges':source[pid]['ranges']} for pid in sorted(referenced_passages(days))}
                references.update(refs)
                data={'schema_version':3,'calendar':CALENDARS[lang],'year':year,'month':month,'days':days,'references':refs}
                validate_month(data,lang,year,month)
                files[f'schedule/{lang}/{year}/{month:02}.json']=encoded(data)
    for translation,edition in EDITIONS.items():
        needed={(ref['book'],c) for ref in references.values() for c1,_,c2,_ in display_ranges(ref,translation) for c in range(c1,c2+1)}
        chapters={}
        for key,verse in verse_snapshot['verses'][translation].items():
            book,chapter,number=map(int,key.split(':'))
            if (book,chapter) in needed:
                chapters.setdefault((book,chapter),[]).append([number,verse['last'],verse['text']])
        for book,chapter in sorted(needed):
            unavailable = ('numbering' if book==19 or (translation=='ubh' and book in (29,39))
                           or f'{book}:{chapter}' in verse_snapshot['numbering'][translation]
                           else 'missing_text' if (book,chapter) not in chapters else None)
            verses=[] if unavailable else sorted(chapters[(book,chapter)])
            audio={}
            for voice in edition['voices']:
                excluded=((voice=='bondarenko' and book in (13,14,22,23))
                          or (voice=='npu_uk' and book not in (19,*range(40,67)))
                          or (voice=='kozlov_uk' and (book,chapter) in ((17,11),(17,12),(27,13),(27,14))))
                audio[voice]=[None if excluded else timings[voice].get(f'{book}:{chapter}:{v[0]}') for v in verses]
            language=edition['language']
            data={'schema_version':3,'translation':translation,'book':book,'chapter':chapter,
                  'book_name':books[str(book)][language],'abbr':books[str(book)][language+'_abbr'],
                  'unavailable':unavailable,'verses':verses,'audio':audio}
            validate_chapter(data,translation,book,chapter)
            files[f'text/{translation}/{book:02}/{chapter:02}.json']=encoded(data)
    return files
