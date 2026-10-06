"""Export only required local alignment rows; never copy audio or mutate the DB."""
from __future__ import annotations
import argparse
import math
import datetime as dt
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sitegen.lectionary_data import SOURCE, load_json, encoded, require
from sitegen.gospel_audio import EDITIONS, valid_timing
from tools.build_reading_time import local_query, canonical_book


def export_timecodes():
    registry = {v: t for t, e in EDITIONS.items() for v in e['voices']}
    actual = local_query('SELECT JSON_ARRAY(v.alias,t.alias) FROM voices v JOIN translations t ON v.translation=t.code WHERE v.active=1 AND t.active=1')
    require(dict(actual) == registry, 'active local voice registry changed; review offered editions')
    verses = load_json(SOURCE / 'verses.json')['verses']
    rows = local_query('SELECT JSON_ARRAY(v.alias,a.book_number,a.chapter_number,a.verse_number,a.begin,a.end) FROM voice_alignments a JOIN voices v ON v.code=a.voice WHERE v.active=1 ORDER BY v.alias,a.book_number,a.chapter_number,a.verse_number')
    result = {voice: {} for voice in registry}
    invalid = {voice: {} for voice in registry}
    for voice, book, chapter, verse, begin, end in rows:
        require(voice in registry, 'unknown local voice')
        key = f'{canonical_book(book)}:{chapter}:{verse}'
        if key not in verses[registry[voice]]:
            continue
        require(key not in result[voice], f'duplicate alignment: {voice}:{key}')
        require(all(type(v) in (int,float) and math.isfinite(v) for v in (begin,end)), f'invalid alignment: {voice}:{key}')
        if not valid_timing(begin,end):
            invalid[voice][key] = [begin,end]
            result[voice][key] = None
        else:
            result[voice][key] = [begin, end]
    data = {'schema_version': 2, 'exported_on': dt.datetime.now(dt.timezone.utc).date().isoformat(),
            'source': 'read-only local cep_public.voice_alignments in cep-mysql', 'voices': registry, 'timecodes': result, 'invalid': invalid}
    (SOURCE / 'timecodes.json').write_bytes(encoded(data))
    names = local_query('SELECT JSON_ARRAY(number,full_name_ru,short_name_ru,full_name_uk,short_name_uk,full_name_en,short_name_en) FROM bible_books ORDER BY number')
    books = {str(canonical_book(b)): dict(zip(('ru','ru_abbr','uk','uk_abbr','en','en_abbr'), labels)) for b, *labels in names}
    require(len(books) == 66 and all(isinstance(x,str) and x.strip() for v in books.values() for x in v.values()), 'invalid book names')
    (SOURCE / 'book-names.json').write_bytes(encoded(books))
    print(f'Explicitly unavailable alignment rows: {sum(len(v) for v in invalid.values())}')
    print(f'Exported {sum(len(v) for v in result.values())} alignment rows for {len(result)} voices')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    export_timecodes()
