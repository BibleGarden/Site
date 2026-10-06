"""Classify captured OCU/UGCC source lines offline, preserving comparison refs."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sitegen.lectionary_data import SOURCE, encoded, load_json, require


# Match service headings, not saints' names or notes mentioning a service.
LITURGY = re.compile(r'^(?:Літ\.|(?:На )?Літургі[яїю]|Вечірня з Літургією)', re.I)
OTHER_SERVICE = re.compile(
    r'^(?:[^:]+:\s*)?(?:Ран\.|Утр\.|На ранній|Веч\.|Вечір|На веч|'
    r'На \d+-му часі|На \d+-[йм] час|Час |Царські часи|'
    r'Під час освячення|На осв\.|На водосвятті|(?:На|По) вмиванні)', re.I)


def is_pair(refs):
    return (len(refs) == 2 and 44 <= refs[0]['book'] <= 65
            and 40 <= refs[1]['book'] <= 43
            and all(type(v) is int and v > 0 for ref in refs
                    for span in ref['ranges'] for v in span))


def liturgy_refs(source, lines):
    require(source in ('ocu', 'ugcc'), f'unknown reading source: {source}')
    selected = []
    active = False
    has_service = False
    for line in lines:
        text = line['text'].strip()
        if LITURGY.match(text):
            active = True
            has_service = True
        elif OTHER_SERVICE.match(text):
            active = False
            has_service = True
        if active:
            selected.extend(line['refs'])
    if has_service:
        return selected

    # Both calendars omit the Liturgy heading for a standalone ordinary pair.
    # Require the source form itself, never substitute the day's broad refs.
    reading_lines = [line for line in lines if line['refs']]
    refs = [ref for line in reading_lines for ref in line['refs']]
    if not is_pair(refs):
        return []
    if source == 'ocu':
        if len(reading_lines) == 1 and re.match(r'^(?:[123] )?[А-ЯЄІЇ][а-яєії]+\.,', reading_lines[0]['text']):
            return refs
    elif (len(reading_lines) == 2
          and reading_lines[0]['text'].startswith('Ап. ')
          and reading_lines[1]['text'].startswith('Єв. ')):
        return refs
    return []


def rebuild(references, snapshots):
    """Retain broad research comparisons; derive only service-specific evidence."""
    for source in ('ocu', 'ugcc'):
        days = snapshots[source]
        require([d['date'] for d in days] == [d['date'] for d in references[source]],
                f'{source}: captured dates changed')
        for record, day in zip(references[source], days):
            refs = [r for line in day['lines'] for r in line['refs']]
            require(refs == record['refs'], f'{source}:{day["date"]}: comparison refs changed')
            record['liturgy_refs'] = liturgy_refs(source, day['lines'])
    return references


def main():
    path = SOURCE / 'references.json'
    references = rebuild(load_json(path), load_json(SOURCE / 'source-readings.json'))
    path.write_bytes(encoded(references))
    print('Regenerated OCU/UGCC liturgical evidence from captured source lines')


if __name__ == '__main__':
    main()
