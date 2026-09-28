"""Build the John 1:1–5 demo from the uncommitted full-chapter recordings.

The source files are named <narrator>.mp3 in --source-dir. Requires ffmpeg and
ffprobe on PATH; both exit failures propagate rather than producing partial data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tools/data"
OUTPUT = ROOT / "static/bible-garden/audio/demo"
MANIFEST = ROOT / "content/bible-garden/demos/multi-reading.json"
NARRATORS = {
    "bsb_souer": {"translation": "bsb", "names": {"en": ["Berean Standard Bible (BSB)", "Bob Souer"], "ru": ["Berean Standard Bible (BSB)", "Bob Souer"], "uk": ["Berean Standard Bible (BSB)", "Bob Souer"]}},
    "prozorovsky": {"translation": "bti", "names": {"en": ["Kulakov translation (Russian)", "Nikita Semyonov-Prozorovsky"], "ru": ["Перевод Кулаковых", "Никита Семёнов-Прозоровский"], "uk": ["Переклад Кулакових (російською)", "Нікіта Семенов-Прозоровський"]}},
    "prudovsky": {"translation": "syn", "names": {"en": ["Russian Synodal Bible", "Ilya Prudovsky"], "ru": ["Синодальный перевод", "Илья Прудовский"], "uk": ["Синодальний переклад (російською)", "Ілля Прудовський"]}},
    "kozlov_uk": {"translation": "ubh", "names": {"en": ["Khomenko translation (Ukrainian)", "Ihor Kozlov"], "ru": ["Перевод Хоменка (украинский)", "Игорь Козлов"], "uk": ["Переклад Хоменка", "Ігор Козлов"]}},
}
PAIRS = {"ru": ["prozorovsky", "bsb_souer"], "en": ["bsb_souer", "prudovsky"], "uk": ["kozlov_uk", "bsb_souer"]}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def source_data() -> tuple[dict, dict]:
    timings = {}
    for row in rows(DATA / "john1-timings.tsv"):
        narrator, verse = row["narrator"], int(row["verse"])
        key = (narrator, verse)
        if narrator not in NARRATORS or not 1 <= verse <= 5 or key in timings:
            raise ValueError(f"invalid or duplicate timing: {key}")
        begin, end = Decimal(row["begin"]), Decimal(row["end"])
        if not begin.is_finite() or not end.is_finite() or begin < 0 or end <= begin:
            raise ValueError(f"invalid interval: {key}")
        timings[key] = (begin, end)
    expected = {(narrator, verse) for narrator in NARRATORS for verse in range(1, 6)}
    if set(timings) != expected:
        raise ValueError("timings must contain every narrator and verse 1–5 exactly once")
    texts = {}
    for row in rows(DATA / "john1-texts.tsv"):
        key = (row["translation"], int(row["verse"]))
        if key in texts or not row["text"].strip():
            raise ValueError(f"invalid or duplicate text: {key}")
        texts[key] = row["text"]
    expected = {(data["translation"], verse) for data in NARRATORS.values() for verse in range(1, 6)}
    if set(texts) != expected:
        raise ValueError("texts must contain every translation and verse 1–5 exactly once")
    return timings, texts


def build(source_dir: Path) -> dict:
    timings, texts = source_data()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    clips = {}
    for narrator, info in NARRATORS.items():
        source = source_dir / f"{narrator}.mp3"
        if not source.is_file():
            raise FileNotFoundError(source)
        narrator_dir = OUTPUT / narrator
        narrator_dir.mkdir(parents=True, exist_ok=True)
        verses = []
        for verse in range(1, 6):
            begin, end = timings[narrator, verse]
            clip_begin = begin - Decimal("0.050")
            clip_end = end + Decimal("0.150")
            if clip_begin < 0:
                raise ValueError(f"{narrator}:{verse}: cannot add leading margin")
            target = narrator_dir / f"{verse}.mp3"
            subprocess.run([
                "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
                "-ss", str(clip_begin), "-t", str(clip_end - clip_begin), "-vn", "-ac", "1", "-ar", "24000",
                "-c:a", "libmp3lame", "-b:a", "56k", "-map_metadata", "-1", str(target),
            ], check=True)
            duration = Decimal(subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target),
            ], capture_output=True, text=True, check=True).stdout.strip())
            if duration < clip_end - clip_begin:
                raise ValueError(f"{target}: shorter than requested verse interval")
            verses.append({
                "path": f"/audio/demo/{narrator}/{verse}.mp3",
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "duration": float(duration),
            })
        clips[narrator] = {
            "translation": info["translation"],
            "names": info["names"],
            "verses": verses,
        }
    data = {"passages": "John 1:1–5", "pairs": PAIRS, "clips": clips,
            "texts": {translation: [texts[translation, verse] for verse in range(1, 6)] for translation in sorted({item["translation"] for item in NARRATORS.values()})}}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for narrator in NARRATORS:
        (OUTPUT / f"{narrator}.mp3").unlink(missing_ok=True)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True, help="directory with full John 1 MP3s")
    build(parser.parse_args().source_dir)
