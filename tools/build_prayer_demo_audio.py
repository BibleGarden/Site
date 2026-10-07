"""Re-cut the approved demo clips from verified local app chapter sources."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(parser_root: Path) -> None:
    path = ROOT / 'content/lampada/demos/prayer-session.json'
    data = json.loads(path.read_text())
    for lang, value in data['locales'].items():
        scripture = value['scripture']
        source_text = json.loads((parser_root / scripture['source']).read_text())
        book = next(b for b in source_text['books'] if b['id'] == scripture['book'])
        chapter = next(c for c in book['chapters'] if c['id'] == scripture['chapter'])
        verse = next(v for v in chapter['verses'] if v['id'] == scripture['verse'])
        if verse['unformatedText'] != scripture['text']:
            raise ValueError(f'{lang}: Scripture differs from verified translation source')
        audio = value['audio']
        if audio['status'] == 'unavailable':
            continue  # Explicit owner-authorized absence, never a replacement recording.
        source = parser_root / audio['source_file']
        if hashlib.sha256(source.read_bytes()).hexdigest() != audio['source_sha256']:
            raise ValueError(f'{lang}: chapter source changed; review text and alignment before resync')
        target = ROOT / 'static/lampada' / audio['path'].lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-ss', str(audio['begin']),
                        '-t', str(audio['end'] - audio['begin']), '-map_metadata', '-1', '-ac', '1',
                        '-ar', '24000', '-b:a', '56k', str(target)], check=True)
        audio['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        audio['duration'] = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                    'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(target)]))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parser-root', type=Path, required=True)
    build(parser.parse_args().parser_root)
