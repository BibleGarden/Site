"""Build the John 1:1-5 Multi Reading demos from uncommitted full-chapter
recordings.

A narrator registry lists every voice with its translation and localized
names; per-demo definitions (id, pairs, title) pick which narrators pair up
in each language. Clips are shared between demos: `static/bible-garden/audio/
demo/<narrator>/<verse>.mp3` is cut once per narrator and reused by every
demo that references it. Each `--source-dir` may hold any subset of the
registered narrators' full-chapter <narrator>.mp3 files; only narrators whose
source file is found get (re)cut, so adding a new demo/narrator does not
require the older sources. ffmpeg is deterministic, so re-cutting an existing
narrator from the same source reproduces byte-identical clips.

Requires ffmpeg and ffprobe on PATH; both exit failures propagate rather than
producing partial data.
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
DEMOS_DIR = ROOT / "content/bible-garden/demos"

# narrator id -> translation alias + localized [translation name, narrator name].
# A `None` narrator name means the publisher does not credit one; render only
# the translation name in that case (see sitegen/multi_reading_demo.py).
NARRATORS: dict[str, dict] = {
    "bsb_souer": {
        "translation": "bsb",
        "names": {
            "en": ["Berean Standard Bible (BSB)", "Bob Souer"],
            "ru": ["Berean Standard Bible (BSB)", "Bob Souer"],
            "uk": ["Berean Standard Bible (BSB)", "Bob Souer"],
        },
    },
    "prozorovsky": {
        "translation": "bti",
        "names": {
            "en": ["Kulakov translation (Russian)", "Nikita Semyonov-Prozorovsky"],
            "ru": ["Перевод Кулаковых", "Никита Семёнов-Прозоровский"],
            "uk": ["Переклад Кулакових (російською)", "Нікіта Семенов-Прозоровський"],
        },
    },
    "bondarenko": {
        "translation": "syn",
        "names": {
            "en": ["Russian Synodal Bible", "Alexander Bondarenko"],
            "ru": ["Синодальный перевод", "Александр Бондаренко"],
            "uk": ["Синодальний переклад (російською)", "Олександр Бондаренко"],
        },
    },
    "prudovsky": {
        "translation": "syn",
        "names": {
            "en": ["Russian Synodal Bible", "Ilya Prudovsky"],
            "ru": ["Синодальный перевод", "Илья Прудовский"],
            "uk": ["Синодальний переклад (російською)", "Ілля Прудовський"],
        },
    },
    "kozlov_uk": {
        "translation": "ubh",
        "names": {
            "en": ["Khomenko translation (Ukrainian)", "Ihor Kozlov"],
            "ru": ["Перевод Хоменка (украинский)", "Игорь Козлов"],
            "uk": ["Переклад Хоменка", "Ігор Козлов"],
        },
    },
    "winfred_henson": {
        "translation": "webus",
        "names": {
            "en": ["World English Bible (WEB)", "Winfred Henson"],
            "ru": ["World English Bible (WEB)", "Winfred Henson"],
            "uk": ["World English Bible (WEB)", "Winfred Henson"],
        },
    },
    "npu_uk": {
        "translation": "npu",
        "names": {
            "en": ["New Ukrainian Translation (NPU)", None],
            "ru": ["Новый перевод на украинский (НПУ)", None],
            "uk": ["Новий переклад українською (НПУ)", None],
        },
    },
}

# Per-demo id: {lang: [first narrator, second narrator]} and localized title.
DEMOS: dict[str, dict] = {
    "multi-reading": {
        "pairs": {
            "ru": ["prozorovsky", "bsb_souer"],
            "en": ["bsb_souer", "prudovsky"],
            "uk": ["kozlov_uk", "bsb_souer"],
        },
        "title": {
            "en": "Listen to John 1:1–5 in two languages",
            "ru": "Послушайте Ин 1:1–5 на двух языках",
            "uk": "Послухайте Ів 1:1–5 двома мовами",
        },
    },
    "translation-compare": {
        "pairs": {
            "ru": ["bondarenko", "prozorovsky"],
            "en": ["bsb_souer", "winfred_henson"],
            "uk": ["kozlov_uk", "npu_uk"],
        },
        "title": {
            "en": "Listen to John 1:1–5 in two translations",
            "ru": "Послушайте Ин 1:1–5 в двух переводах",
            "uk": "Послухайте Ів 1:1–5 у двох перекладах",
        },
    },
}

PASSAGE = "John 1:1–5"


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
        raise ValueError("timings must contain every narrator and verse 1-5 exactly once")
    texts = {}
    for row in rows(DATA / "john1-texts.tsv"):
        key = (row["translation"], int(row["verse"]))
        if key in texts or not row["text"].strip():
            raise ValueError(f"invalid or duplicate text: {key}")
        texts[key] = row["text"]
    expected = {(data["translation"], verse) for data in NARRATORS.values() for verse in range(1, 6)}
    if set(texts) != expected:
        raise ValueError("texts must contain every translation and verse 1-5 exactly once")
    return timings, texts


def cut_clips(narrator: str, source: Path, timings: dict) -> None:
    narrator_dir = OUTPUT / narrator
    narrator_dir.mkdir(parents=True, exist_ok=True)
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


def clip_info(narrator: str, timings: dict) -> list[dict]:
    narrator_dir = OUTPUT / narrator
    verses = []
    for verse in range(1, 6):
        target = narrator_dir / f"{verse}.mp3"
        if not target.is_file():
            raise FileNotFoundError(
                f"{target}: missing; run with --source-dir containing {narrator}.mp3 first"
            )
        duration = Decimal(subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target),
        ], capture_output=True, text=True, check=True).stdout.strip())
        begin, end = timings[narrator, verse]
        if duration < end - begin:
            raise ValueError(f"{target}: shorter than requested verse interval")
        verses.append({
            "path": f"/audio/demo/{narrator}/{verse}.mp3",
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "duration": float(duration),
        })
    return verses


def build(source_dirs: list[Path]) -> dict[str, dict]:
    timings, texts = source_data()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    sources: dict[str, Path] = {}
    for source_dir in source_dirs:
        for narrator in NARRATORS:
            candidate = source_dir / f"{narrator}.mp3"
            if candidate.is_file():
                sources[narrator] = candidate
    for narrator, source in sources.items():
        cut_clips(narrator, source, timings)

    clips_by_narrator = {narrator: clip_info(narrator, timings) for narrator in NARRATORS}

    manifests = {}
    for demo_id, demo in DEMOS.items():
        narrators_used = sorted({narrator for pair in demo["pairs"].values() for narrator in pair})
        clips = {
            narrator: {
                "translation": NARRATORS[narrator]["translation"],
                "names": NARRATORS[narrator]["names"],
                "verses": clips_by_narrator[narrator],
            }
            for narrator in narrators_used
        }
        translations_used = sorted({NARRATORS[narrator]["translation"] for narrator in narrators_used})
        data = {
            "title": demo["title"],
            "passages": PASSAGE,
            "pairs": demo["pairs"],
            "clips": clips,
            "texts": {
                translation: [texts[translation, verse] for verse in range(1, 6)]
                for translation in translations_used
            },
        }
        manifest = DEMOS_DIR / f"{demo_id}.json"
        DEMOS_DIR.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifests[demo_id] = data

    for narrator in NARRATORS:
        (OUTPUT / f"{narrator}.mp3").unlink(missing_ok=True)
    return manifests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path, action="append", required=True, dest="source_dirs",
        help="directory with full John 1 MP3s named <narrator>.mp3; may be given more than once",
    )
    build(parser.parse_args().source_dirs)
