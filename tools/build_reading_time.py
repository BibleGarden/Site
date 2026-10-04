"""Export local cep_public and fully decoded audio, or rebuild JSON from chapter TSVs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sitegen.errors import BuildError
from sitegen.reading_plan import CHAPTER_COUNTS, SOURCE_NT, load_chapters
from tools.build_demo_audio import NARRATORS

DATA = ROOT / 'tools/data/reading-time'
OUTPUT = ROOT / 'content/bible-garden/calculator/reading-time.json'
UNITS = ('verse', 'paragraph', 'section', 'chapter')
LANGS = {'syn': 'ru', 'bti': 'ru', 'bsb': 'en', 'webus': 'en', 'webbe': 'en', 'ubh': 'uk', 'npu': 'uk'}
VOICE_BOOKS = {v: set(range(1, 67)) for v in NARRATORS}
VOICE_BOOKS['bondarenko'] -= {13, 14, 22, 23}
VOICE_BOOKS['npu_uk'] = {19, *range(40, 67)}
VOICE_FIELDS = ['voice', 'book', 'chapter', 'decoded_seconds'] + [f'{u}_{k}' for u in UNITS for k in ('count', 'seconds')]
ANOMALY_FIELDS = ['type', 'voice', 'book', 'chapter', 'unit', 'first_verse', 'last_verse', 'decoded_seconds', 'alignment_end_seconds', 'difference_seconds', 'bad_packets', 'error_lines']


def chapter_count(translation: str, book: int) -> int:
    return 3 if translation == 'ubh' and book == 39 else CHAPTER_COUNTS[book - 1]


def canonical_book(source_book: int) -> int:
    if not 1 <= source_book <= 66:
        raise BuildError(f'invalid source book {source_book}')
    return SOURCE_NT[source_book - 45][1] if source_book >= 45 else source_book


def source_book(book: int) -> int:
    return next(i + 45 for i, (_name, b) in enumerate(SOURCE_NT) if b == book) if book >= 45 else book


def ranges(verses: list, unit: str) -> list[tuple[int, int]]:
    """iOS units include the first block of every chapter, even without a heading."""
    if not verses:
        raise BuildError('empty chapter')
    if unit == 'verse':
        return [(i, i) for i in range(len(verses))]
    starts = [0]
    if unit != 'chapter':
        flag = 2 if unit == 'paragraph' else 3
        starts += [i for i, verse in enumerate(verses) if i and verse[flag]]
    return [(a, b - 1) for a, b in zip(starts, starts[1:] + [len(verses)])]


def span_sum(audio: list[tuple[float, float]], blocks: list[tuple[int, int]], duration: float, empty_windows: list | None = None) -> float:
    total = 0.0
    for first, last in blocks:
        # The app clamps the first translation's indices to the second's last verse.
        first, last = min(first, len(audio) - 1), min(last, len(audio) - 1)
        begin = max(audio[first][0] - .2, audio[first - 1][1] if first else 0, 0)
        end = audio[last][1]
        if audio[first][0] < 0 or audio[last][1] < audio[last][0]:
            raise BuildError(f'invalid alignment at indices {first}–{last}')
        if end < begin and empty_windows is not None:
            empty_windows.append((first,last,begin,end))
        # Empty intersections from overlapping verse windows are zero in the app.
        total += max(0, min(end, duration) - min(begin, duration))
    return total


def mp3_payload(blob: bytes) -> tuple[bytes, int]:
    """Remove only ID3 metadata, without modifying or validating MPEG audio.

    David's concatenated verse files contain this exact encoder tag internally.
    Removing its complete 45-byte signature cannot remove an audio frame. Other
    data remains unchanged; ffmpeg measures the audio it can actually decode.
    """
    tags = 0
    while blob.startswith(b'ID3'):
        header = blob[:10]
        if len(header) != 10 or header[3] not in (2,3,4) or any(b & 128 for b in header[6:10]):
            raise BuildError('invalid ID3 header')
        size = 10 + sum(b << shift for b,shift in zip(header[6:10], (21,14,7,0)))
        if header[3] == 4 and header[5] & 16:
            size += 10
        if size > len(blob):
            raise BuildError('truncated ID3 tag')
        blob = blob[size:]
        tags += 1
    encoder_tag = b'ID3\x04\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf59.27.100' + bytes(11)
    tags += blob.count(encoder_tag)
    return blob.replace(encoder_tag,b''), tags


def decode(path: Path, *, strict: bool = False) -> tuple[float, str, int, int]:
    if not path.is_file():
        raise BuildError(f'missing chapter audio: {path}')
    blob = path.read_bytes()
    try:
        payload, _tags = mp3_payload(blob)
    except BuildError as error:
        raise BuildError(f'{path}: {error}') from error
    options = ['-xerror', '-err_detect', 'explode'] if strict else []
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'repeat+error', *options, '-f', 'mp3', '-i', 'pipe:0', '-map', '0:a:0', '-f', 'null', '-progress', 'pipe:1', '-'], input=payload, capture_output=True)
    diagnostics = result.stderr.decode()
    if result.returncode:
        raise BuildError(f'decoder failed with exit {result.returncode}: {path}: {diagnostics.strip()}')
    times = [int(line.split(b'=', 1)[1]) for line in result.stdout.splitlines() if line.startswith(b'out_time_us=')]
    if not times or times[-1] <= 0:
        raise BuildError(f'decoder produced no audio: {path}: {diagnostics.strip()}')
    if strict and diagnostics.strip():
        raise BuildError(f'strict decoder error in {path}: {diagnostics.strip()}')
    bad_packets = diagnostics.count('Error submitting packet to decoder')
    if not bad_packets:
        bad_packets = diagnostics.count('Header missing')
    return times[-1] / 1e6, hashlib.sha256(blob).hexdigest(), bad_packets, len(diagnostics.splitlines())


def local_query(sql: str) -> list:
    """The only connection is the local container; credentials never reach argv or output."""
    settings = Path('/root/cep/Bible-API/.env').read_text().splitlines()
    values = [shlex.split(line.split('=', 1)[1], comments=True) for line in settings if line.startswith('DB_PASSWORD=')]
    if len(values) != 1 or len(values[0]) != 1:
        raise BuildError('local Bible-API/.env: invalid DB_PASSWORD')
    password = values[0][0]
    if not password:
        raise BuildError('local Bible-API/.env: missing DB_PASSWORD')
    result = subprocess.run(['docker', 'exec', '-i', '-e', 'MYSQL_PWD', 'cep-mysql', 'mysql', '--default-character-set=utf8mb4', '--batch', '--raw', '--skip-column-names', '-uroot', 'cep_public'], input='SET SESSION TRANSACTION READ ONLY; START TRANSACTION;\n' + sql + ';\nCOMMIT;\n', env=dict(os.environ, MYSQL_PWD=password), capture_output=True, text=True)
    if result.returncode:
        raise BuildError(f'local read-only SQL failed: {result.stderr.strip()}')
    return [json.loads(line) for line in result.stdout.splitlines()]


def write_tsv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fields, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def export_local(audio_root: Path, workers: int) -> None:
    started = time.monotonic()
    voices = local_query('SELECT JSON_ARRAY(v.alias,v.code,t.alias,t.code) FROM voices v JOIN translations t ON v.translation=t.code WHERE v.active=1 AND t.active=1 ORDER BY v.alias')
    registry = {v[0]: v for v in voices}
    if set(registry) != set(NARRATORS) or any(registry[v][2] != NARRATORS[v]['translation'] for v in registry):
        raise BuildError('local voice registry differs from the nine supported voices')
    verses = local_query('SELECT JSON_ARRAY(v.translation,v.book_number,v.chapter_number,v.verse_number,v.verse_number_join,v.start_paragraph,tt.before_translation_verse IS NOT NULL) FROM translation_verses v JOIN translations t ON t.code=v.translation LEFT JOIN (SELECT DISTINCT before_translation_verse FROM translation_titles) tt ON tt.before_translation_verse=v.code WHERE t.active=1 ORDER BY v.translation,v.book_number,v.chapter_number,v.verse_number')
    tid = {v[3]: v[2] for v in voices}
    vid = {v[1]: v[0] for v in voices}
    texts = defaultdict(list)
    for t, b, c, number, join, paragraph, title in verses:
        translation = tid[t]
        book = canonical_book(b)
        if (translation=='npu' and book not in VOICE_BOOKS['npu_uk']) or c > chapter_count(translation, book):
            continue
        if c < 1 or number < 1:
            raise BuildError('invalid text chapter or verse')
        texts[translation, book, c].append((number, join, paragraph, title))
    for rows in texts.values():
        rows.sort(key=lambda row: (row[0] + row[1], row[0]))
    alignments = local_query('SELECT JSON_ARRAY(voice,book_number,chapter_number,verse_number,begin,end) FROM voice_alignments ORDER BY voice,book_number,chapter_number,verse_number')
    aligned = defaultdict(dict)
    for v, b, c, number, begin, end in alignments:
        if v not in vid:
            continue
        voice = vid[v]
        book = canonical_book(b)
        translation = NARRATORS[voice]['translation']
        if book not in VOICE_BOOKS[voice] or c > chapter_count(translation, book):
            continue
        begin, end = float(begin), float(end)
        if not math.isfinite(begin) or not math.isfinite(end) or begin < 0 or end < begin:
            raise BuildError(f'invalid alignment {voice}:{book}:{c}:{number}')
        if number in aligned[voice, book, c]:
            raise BuildError(f'duplicate alignment {voice}:{book}:{c}:{number}')
        aligned[voice, book, c][number] = (begin, end)
    expected = {(v, b, c) for v in NARRATORS for b in VOICE_BOOKS[v] for c in range(1, chapter_count(NARRATORS[v]['translation'], b) + 1)}
    if set(aligned) != expected:
        raise BuildError(f'chapter coverage mismatch: missing={sorted(expected-set(aligned))}, extra={sorted(set(aligned)-expected)}')
    paths = {k: audio_root / NARRATORS[k[0]]['translation'] / k[0] / 'mp3' / f'{source_book(k[1]):02d}' / f'{k[2]:02d}.mp3' for k in sorted(aligned)}
    strict_sample = []
    for voice in sorted(NARRATORS):
        key = voice, 43, 1
        normal, strict = decode(paths[key]), decode(paths[key],strict=True)
        if normal[0] != strict[0] or normal[2:] != (0,0):
            raise BuildError(f'clean-sample decoder comparison failed: {voice}')
        strict_sample.append(dict(voice=voice,book=43,chapter=1,normal_seconds=normal[0],strict_seconds=strict[0]))
    print(f'Clean decoder sample: {len(strict_sample)} files have identical normal/strict lengths',flush=True)
    print(f'Fully decoding {len(paths)} chapters with {workers} workers', flush=True)
    decoded = {}
    failures = []
    def inspect(path):
        try:
            return decode(path), None
        except BuildError as error:
            return None, str(error)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (key, (value,error)) in enumerate(zip(paths, pool.map(inspect, paths.values())), 1):
            if error:
                failures.append(error)
            else:
                decoded[key] = value
            if index % 500 == 0:
                print(f'decoded {index}/{len(paths)} ({time.monotonic()-started:.1f}s)', flush=True)
    if failures:
        raise BuildError(f'full decoding failed in {len(failures)} chapters after {time.monotonic()-started:.3f}s:\n' + '\n'.join(failures))
    voice_rows, anomalies = [], []
    audio_by_chapter = {}
    for key, (duration, digest, bad_packets, error_lines) in decoded.items():
        voice, book, chapter = key
        rows = texts[NARRATORS[voice]['translation'], book, chapter]
        # All spoken rows must have text. Unvoiced text rows are not audio units.
        spoken = [r for r in rows if r[0] in aligned[key]]
        if len(spoken) != len(aligned[key]):
            raise BuildError(f'alignment without text: {key}')
        audio = [aligned[key][r[0]] for r in spoken]
        audio_by_chapter[key] = audio
        row = dict(voice=voice, book=book, chapter=chapter, decoded_seconds=round(duration, 6))
        for unit in UNITS:
            blocks = ranges(spoken, unit)
            row[f'{unit}_count'] = len(blocks)
            empty_windows = []
            try:
                row[f'{unit}_seconds'] = round(span_sum(audio, blocks, duration, empty_windows), 6)
            except BuildError as error:
                raise BuildError(f'{voice}:{book}:{chapter}:{unit}: {error}') from error
            for first,last,begin,end in empty_windows:
                anomalies.append(dict(type='empty_window',voice=voice,book=book,chapter=chapter,unit=unit,first_verse=spoken[first][0],last_verse=spoken[last][0],decoded_seconds=duration,alignment_end_seconds=end,difference_seconds=round(end-begin,6),bad_packets=0,error_lines=0))
        voice_rows.append(row)
        if bad_packets or error_lines:
            anomalies.append(dict(type='decoder_errors',voice=voice,book=book,chapter=chapter,unit='',first_verse='',last_verse='',decoded_seconds=duration,alignment_end_seconds='',difference_seconds='',bad_packets=bad_packets,error_lines=error_lines))
        alignment_end = max(end for _begin, end in audio)
        if abs(duration - alignment_end) > 20:
            anomalies.append(dict(type='duration_mismatch',voice=voice, book=book, chapter=chapter,unit='',first_verse='',last_verse='', decoded_seconds=duration, alignment_end_seconds=alignment_end, difference_seconds=round(duration-alignment_end, 6),bad_packets=0,error_lines=0))
    comparisons = []
    by_key = {(r['voice'], r['book'], r['chapter']): r for r in voice_rows}
    for first, second in [('prudovsky', 'bsb_souer'), ('kozlov_uk', 'bsb_souer')]:
        for unit in ('verse', 'paragraph'):
            exact, approximate = 0.0, 0.0
            exact_count, approximate_count = 0, 0
            for key, row in by_key.items():
                voice, book, chapter = key
                if voice != first:
                    continue
                target = second, book, chapter
                if target not in decoded:
                    raise BuildError(f'pair comparison missing chapter {target}')
                spoken = [r for r in texts[NARRATORS[first]['translation'],book,chapter] if r[0] in aligned[key]]
                exact += row[f'{unit}_seconds'] + span_sum(audio_by_chapter[target], ranges(spoken, unit), decoded[target][0])
                approximate += row[f'{unit}_seconds'] + by_key[target][f'{unit}_seconds']
                exact_count += 2 * row[f'{unit}_count']
                approximate_count += row[f'{unit}_count'] + by_key[target][f'{unit}_count']
            # Include any second-only chapter (UBH merges Malachi 3–4).
            approximate += sum(r[f'{unit}_seconds'] for k, r in by_key.items() if k[0] == second and (first,k[1],k[2]) not in by_key)
            approximate_count += sum(r[f'{unit}_count'] for k, r in by_key.items() if k[0] == second and (first,k[1],k[2]) not in by_key)
            comparisons.append(dict(pause_2s_deviation_seconds=round((approximate+2*approximate_count)-(exact+2*exact_count),6), pause_2s_deviation_percent=round(100*((approximate+2*approximate_count)/(exact+2*exact_count)-1),6), pair=f'{first}+{second}', unit=unit, exact_seconds=round(exact,6), approximate_seconds=round(approximate,6), deviation_seconds=round(approximate-exact,6), deviation_percent=round(100*(approximate/exact-1),6)))
    DATA.mkdir(parents=True, exist_ok=True)
    for name, fields, rows in [('voices.tsv',VOICE_FIELDS,voice_rows),('alignment-anomalies.tsv',ANOMALY_FIELDS,anomalies)]:
        write_tsv(DATA/name, fields, rows)
    ffmpeg_version = subprocess.run(['ffmpeg','-version'],check=True,capture_output=True,text=True).stdout.splitlines()[0]
    manifest = dict(schema_version=2, measured_on=datetime.now(timezone.utc).date().isoformat(), source='local cep_public in cep-mysql; local bible-parser/audio', method='normal ffmpeg decoding out_time_us after removing ID3 metadata; clipped and empty iOS spans; own-translation units', workers=workers, ffmpeg_version=ffmpeg_version, export_seconds=round(time.monotonic()-started,3), chapter_count=len(decoded), strict_sample=strict_sample, anomaly_count=len(anomalies), anomaly_counts={kind:sum(r['type']==kind for r in anomalies) for kind in ('duration_mismatch','empty_window','decoder_errors')}, bad_packets=sum(v[2] for v in decoded.values()), comparisons=comparisons, source_fingerprint=hashlib.sha256(json.dumps([verses,alignments,[(str(k),*values) for k,values in decoded.items()]],ensure_ascii=False).encode()).hexdigest(), files={name: hashlib.sha256((DATA/name).read_bytes()).hexdigest() for name in ('voices.tsv','alignment-anomalies.tsv')})
    (DATA/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Export: {manifest["export_seconds"]}s; anomalies={manifest["anomaly_counts"]}; bad packets={manifest["bad_packets"]}', flush=True)
    for item in comparisons:
        print(f'Approximation {item["pair"]} {item["unit"]}: {item["deviation_seconds"]:+.3f}s ({item["deviation_percent"]:+.6f}%)', flush=True)


def read_tsv(path: Path, fields: list[str]) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        if reader.fieldnames != fields:
            raise BuildError(f'{path}: invalid TSV columns')
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise BuildError(f'{path}: malformed row')
        return rows


def build_data() -> dict:
    manifest = json.loads((DATA/'manifest.json').read_text())
    if manifest['schema_version'] != 2 or set(manifest['files']) != {'voices.tsv','alignment-anomalies.tsv'}:
        raise BuildError('reading-time manifest: unsupported version or file list')
    for name, digest in manifest['files'].items():
        if hashlib.sha256((DATA/name).read_bytes()).hexdigest() != digest:
            raise BuildError(f'{DATA/name}: checksum mismatch')
    names = {c.book:c.names for c in load_chapters()}
    data = dict(schema_version=2,measured_on=manifest['measured_on'],method='mp3-decoded',books=[dict(id=b,names=names[b],chapters=CHAPTER_COUNTS[b-1]) for b in range(1,67)],voices={})
    for voice,info in NARRATORS.items():
        data['voices'][voice] = dict(lang=LANGS[info['translation']],names={lang:' · '.join(x for x in info['names'][lang] if x) for lang in ('en','ru','uk')},books={})
    seen = set()
    for row in read_tsv(DATA/'voices.tsv',VOICE_FIELDS):
        voice = row['voice']
        if voice not in NARRATORS:
            raise BuildError(f'voices.tsv: unknown voice {voice}')
        book,chapter = int(row['book']),int(row['chapter'])
        translation = NARRATORS[voice]['translation']
        if book not in VOICE_BOOKS[voice] or not 1<=chapter<=chapter_count(translation,book) or (voice,book,chapter) in seen:
            raise BuildError(f'voices.tsv: invalid or duplicate chapter {voice}:{book}:{chapter}')
        seen.add((voice,book,chapter))
        target = data['voices'][voice]['books'].setdefault(str(book),dict(chapters=0,seconds=0,units={u:dict(count=0,seconds=0) for u in UNITS}))
        seconds = float(row['decoded_seconds'])
        if not math.isfinite(seconds) or seconds<=0:
            raise BuildError('voices.tsv: invalid decoded_seconds')
        target['chapters'] += 1
        target['seconds'] += seconds
        for unit in UNITS:
            count,span = int(row[f'{unit}_count']),float(row[f'{unit}_seconds'])
            if count<1 or (unit=='chapter' and count!=1) or not math.isfinite(span) or span<0 or span>seconds+.001:
                raise BuildError('voices.tsv: invalid unit count or seconds')
            target['units'][unit]['count'] += count
            target['units'][unit]['seconds'] += span
    expected = {(v,b,c) for v in VOICE_BOOKS for b in VOICE_BOOKS[v] for c in range(1,chapter_count(NARRATORS[v]['translation'],b)+1)}
    if seen!=expected:
        raise BuildError('voices.tsv: chapter coverage mismatch')
    for voice in data['voices'].values():
        for book in voice['books'].values():
            book['seconds'] = round(book['seconds'],6)
            for unit in book['units'].values():
                unit['seconds'] = round(unit['seconds'],6)
    from sitegen.reading_time import validate_data
    validate_data(data)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-local', action='store_true')
    parser.add_argument('--decode', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--audio-root', type=Path, default=Path('/root/cep/bible-parser/audio'))
    args = parser.parse_args()
    if args.export_local != args.decode or not 1 <= args.workers <= 32:
        parser.error('--export-local and --decode must be used together; workers must be 1–32')
    try:
        if args.export_local:
            export_local(args.audio_root, args.workers)
        started = time.monotonic()
        data = build_data()
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
        print(f'Wrote {OUTPUT.relative_to(ROOT)} in {time.monotonic()-started:.3f}s')
    except (BuildError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f'error: {error}\n')


if __name__ == '__main__':
    main()
