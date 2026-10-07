"""Re-cut the approved demo clips from verified local app chapter sources."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_by_id(items: list, item_id: int, label: str) -> dict:
    item = next((item for item in items if item.get('id') == item_id), None)
    if item is None:
        raise ValueError(f'{label}: missing id {item_id}')
    return item


def build(parser_root: Path) -> None:
    path = ROOT / 'content/lampada/demos/prayer-session.json'
    data = json.loads(path.read_text())
    for lang, value in data['locales'].items():
        scripture = value['scripture']
        source_text = json.loads((parser_root / scripture['source']).read_text())
        book = find_by_id(source_text['books'], scripture['book'], f'{lang}: text book')
        chapter = find_by_id(book['chapters'], scripture['chapter'], f'{lang}: text chapter')
        verse = find_by_id(chapter['verses'], scripture['verse'], f'{lang}: text verse')
        if verse['unformatedText'] != scripture['text']:
            raise ValueError(f'{lang}: Scripture differs from verified translation source')
        audio = value['audio']
        if audio['status'] == 'unavailable':
            continue  # Explicit owner-authorized absence, never a replacement recording.
        source = parser_root / audio['source_file']
        if hashlib.sha256(source.read_bytes()).hexdigest() != audio['source_sha256']:
            raise ValueError(f'{lang}: chapter source changed; review text and alignment before resync')
        timings = json.loads((source.parents[2] / 'timecodes.json').read_text())
        timing_book = find_by_id(timings['books'], scripture['book'], f'{lang}: timing book')
        timing_chapter = find_by_id(timing_book['chapters'], scripture['chapter'], f'{lang}: timing chapter')
        timing = find_by_id(timing_chapter['verses'], scripture['verse'], f'{lang}: timing verse')
        if (timing['begin'], timing['end']) != (audio['begin'], audio['end']):
            raise ValueError(f'{lang}: committed interval differs from source timecodes')
        target = ROOT / 'static/lampada' / audio['path'].lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-ss', str(audio['begin']),
                        '-t', str(audio['end'] - audio['begin']), '-map_metadata', '-1', '-ac', '1',
                        '-ar', '24000', '-b:a', '56k', '-fflags', '+bitexact', '-flags:a', '+bitexact',
                        '-id3v2_version', '0', '-write_id3v1', '0', str(target)], check=True)
        metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(target)]))
        if metadata['format'].get('tags') or b'TSSE' in target.read_bytes():
            raise ValueError(f'{lang}: unexpected metadata in verse clip')
        audio['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        audio['duration'] = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                    'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(target)]))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parser-root', type=Path, required=True)
    build(parser.parse_args().parser_root)
