"""Build passage-based article audio demos from uncommitted full-chapter
recordings.

A narrator registry lists every voice with its translation and localized
names; per-demo definitions select narrators in each language. Per-verse clips
under `static/bible-garden/audio/demo/[<passage>/]<narrator>/<verse>.mp3`
are shared by demos of the same passage. Voices demos also use continuous passage clips. Each
`--source-dir` may hold any subset of the
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
    "bsb_david": {
        "translation": "bsb",
        "names": {lang: ["Berean Standard Bible (BSB)", "David"] for lang in ("en", "ru", "uk")},
    },
    "web_british": {
        "translation": "webbe",
        "names": {lang: ["World English Bible, British Edition (WEBBE)", None] for lang in ("en", "ru", "uk")},
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

JOHN = {"book": 43, "chapters": {data["translation"]: 1 for data in NARRATORS.values()},
        "verses": list(range(1, 6)), "audio_dir": ""}
PSALM = {"book": 19, "chapters": {translation: (22 if translation in {"syn", "bti", "npu"} else 23)
                               for translation in JOHN["chapters"]},
         "verses": list(range(1, 7)), "audio_dir": "psalm23"}
PASSAGES = {"john1": JOHN, "psalm23": PSALM}

# Per-demo id: kind (`multi-reading` pairs or `voices` rows), narrators and localized title.
DEMOS: dict[str, dict] = {
    "multi-reading": {
        "kind": "multi-reading",
        "passage": "john1",
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
        "kind": "multi-reading",
        "passage": "john1",
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
    "narrators": {
        "kind": "voices",
        "passage": "john1",
        "rows": {
            "ru": ["bondarenko", "prudovsky", "prozorovsky"],
            "en": ["bsb_souer", "bsb_david", "winfred_henson", "web_british"],
            "uk": ["kozlov_uk", "npu_uk"],
        },
        "title": {
            "ru": "Послушайте Ин 1:1–5 в чтении каждого диктора",
            "en": "Listen to John 1:1–5 read by each narrator",
            "uk": "Послухайте Ів 1:1–5 у читанні кожного диктора",
        },
    },
}

for lang, narrators, title in (
    ("ru", ["prudovsky", "bondarenko", "prozorovsky"], "Послушайте Пс 22 в чтении каждого диктора"),
    ("en", ["bsb_souer", "bsb_david", "winfred_henson", "web_british"], "Listen to Psalm 23 read by each narrator"),
    ("uk", ["kozlov_uk", "npu_uk"], "Послухайте псалом «Господь — мій пастир» у двох перекладах"),
):
    DEMOS[f"psalm23-voices-{lang}"] = {
        "kind": "voices", "passage": "psalm23", "rows": {lang: narrators}, "title": {lang: title},
    }

# Demo kind -> the definition key holding its narrator selection per language.
DEMO_SELECTIONS = {"multi-reading": "pairs", "voices": "rows"}

MUSIC_NOTES = {
    "ru": ("с музыкой", "без музыки"),
    "en": ("with music", "voice only"),
    "uk": ("з музикою", "без музики"),
}

# These fingerprints pin the timelines used for the committed clips. Manifests
# deliberately contain only player data, so they cannot carry extra generator
# metadata. When a timeline changes, its clips must be re-cut from the source
# instead of silently reusing clips made for the previous timeline.
REUSABLE_TIMING_FINGERPRINTS = {
    "bsb_souer": "9b0248428a492b2ff7a303b04ae122b0159caa35b3cc854b71bb766513ae62b7",
    "prozorovsky": "f4e2dc8e46b142bee59696e99e1582bf856c3f2947bba6f522d11b8400f15167",
    "bondarenko": "de73f7a31176dd1de498d2d4a3df43b4ddfc88cc95cc21cc13a5500caf553a6b",
    "prudovsky": "5b7624a3978278529762103e714271c235618c66d8bbfed6339f063de82c430d",
    "kozlov_uk": "dc7ca5f9495f812fab2f5c94a4be7830ecc48562625decb37a59a18e013ac10c",
    "winfred_henson": "6cb3bc841e21dd3a9fa5b2788534cd168bffaa2cf74a63fcf633550abe44c53d",
    "npu_uk": "3ef99bd03b20bf22f81184295eebe6b2a6c90ab62492113a540fe8fee3328848",
    "bsb_david": "68b0daf5dc3d015f4dc14c50a4da743a57406f7384c46dc2756278f673c0763e",
    "web_british": "de3d2b78bc5eaae12466ef285862c5e67315b0fbafd2ccb24ea9fcc3b893a897",
}

PSALM_TIMING_FINGERPRINTS = {
    "bondarenko": "ed1d91e966642ea79c1ab40474121e08745e2fd1bc3ec136ca2bdcdd121cc6b0",
    "bsb_david": "09807488ef758695c1a54961c493c39f183ac492e48ba22f7f07c7d2f41dc37e",
    "bsb_souer": "8aa9bec80e26f14d8de9a560169c4c87269d34d3a11792d0e12012a994d7eef7",
    "kozlov_uk": "3f83b751981e7dd33d72a83c20365f2875da13c0e4b364964963a9c8bbbc2ce0",
    "npu_uk": "164b616a5e228ce8650af21c24a01bfb31da3bad3739316fcb010fed0ed48fba",
    "prozorovsky": "13f5bdd52cadc7e6345c853e975b94d6880968ceff9b9089955152beb5f81df4",
    "prudovsky": "73dac4dc9394d1877942045d35ce310a3dc85ca38b9b544f81dc7305e7b8fccd",
    "web_british": "e802d7fadf0bf4e91f011cf99299f800be3da7c1656f630bf48d66171e8d0a87",
    "winfred_henson": "1ca6feed1125b80f0c631471f9a98714351ac562aeb3178b673c35a71edb9472",
}

TIMING_FINGERPRINTS = {"john1": REUSABLE_TIMING_FINGERPRINTS, "psalm23": PSALM_TIMING_FINGERPRINTS}


def data_id(passage: dict) -> str:
    return next(key for key, value in PASSAGES.items() if value == passage)


def audio_output(passage: dict) -> Path:
    return OUTPUT / passage["audio_dir"]


def audio_url(passage: dict) -> str:
    return "/audio/demo" + ("/" + passage["audio_dir"] if passage["audio_dir"] else "")


def verse_span(passage: dict) -> str:
    return f'{passage["verses"][0]}-{passage["verses"][-1]}'


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def source_data(passage: dict = JOHN) -> tuple[dict, dict]:
    timings = {}
    for row in rows(DATA / f"{data_id(passage)}-timings.tsv"):
        narrator, verse = row["narrator"], int(row["verse"])
        key = (narrator, verse)
        if narrator not in NARRATORS or verse not in passage["verses"] or key in timings:
            raise ValueError(f"invalid or duplicate timing: {key}")
        if "chapter" in row and int(row["chapter"]) != passage["chapters"][NARRATORS[narrator]["translation"]]:
            raise ValueError(f"wrong chapter for timing: {key}")
        begin, end = Decimal(row["begin"]), Decimal(row["end"])
        if not begin.is_finite() or not end.is_finite() or begin < 0 or end <= begin:
            raise ValueError(f"invalid interval: {key}")
        timings[key] = (begin, end)
    expected = {(narrator, verse) for narrator in NARRATORS for verse in passage["verses"]}
    if set(timings) != expected:
        raise ValueError("timings must contain every narrator and selected verses exactly once")
    texts = {}
    for row in rows(DATA / f"{data_id(passage)}-texts.tsv"):
        key = (row["translation"], int(row["verse"]))
        if key in texts or not row["text"].strip():
            raise ValueError(f"invalid or duplicate text: {key}")
        if "chapter" in row and int(row["chapter"]) != passage["chapters"][row["translation"]]:
            raise ValueError(f"wrong chapter for text: {key}")
        texts[key] = row["text"]
    expected = {(data["translation"], verse) for data in NARRATORS.values() for verse in passage["verses"]}
    if set(texts) != expected:
        raise ValueError("texts must contain every translation and selected verses exactly once")
    return timings, texts


def timing_fingerprint(narrator: str, timings: dict, passage: dict = JOHN) -> str:
    values = "\n".join(
        f"{verse}\t{timings[narrator, verse][0]}\t{timings[narrator, verse][1]}"
        for verse in passage["verses"]
    )
    return hashlib.sha256(values.encode()).hexdigest()


def recorded_clips(passage: dict = JOHN) -> dict[str, list[list[dict]]]:
    records = {narrator: [] for narrator in NARRATORS}
    for demo_id, demo in DEMOS.items():
        if PASSAGES[demo["passage"]] != passage:
            continue
        manifest = DEMOS_DIR / f"{demo_id}.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            clips = data["clips"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{manifest}: invalid existing manifest") from error
        if not isinstance(clips, dict):
            raise ValueError(f"{manifest}: invalid existing manifest clips")
        for narrator, clip in clips.items():
            if narrator not in records or not isinstance(clip, dict):
                raise ValueError(f"{manifest}: invalid existing narrator {narrator!r}")
            verses = clip.get("verses")
            if not isinstance(verses, list) or len(verses) != len(passage["verses"]):
                raise ValueError(f"{manifest}: invalid existing clips for {narrator}")
            records[narrator].append(verses)
    return records


def recorded_continuous(passage: dict = JOHN) -> dict[str, dict]:
    records = {}
    for demo_id, demo in DEMOS.items():
        if demo["kind"] != "voices" or PASSAGES[demo["passage"]] != passage:
            continue
        manifest = DEMOS_DIR / f"{demo_id}.json"
        if not manifest.is_file():
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for narrator, clip in data["clips"].items():
            record = clip["continuous"]
            if narrator in records and records[narrator] != record:
                raise ValueError(f"{manifest}: conflicting continuous clip for {narrator}")
            records[narrator] = record
    return records


def validate_reused_clips(narrator: str, clips: list[dict], records: list[list[dict]], timings: dict, passage: dict = JOHN) -> None:
    source_hint = f"pass a --source-dir containing {narrator}.mp3"
    if timing_fingerprint(narrator, timings, passage) != TIMING_FINGERPRINTS[data_id(passage)][narrator]:
        raise ValueError(f"{narrator}: timings changed; {source_hint}")
    if not records:
        raise ValueError(f"{narrator}: no existing manifest records; {source_hint}")
    for recorded in records:
        for verse, (clip, previous) in enumerate(zip(clips, recorded), 1):
            if not isinstance(previous, dict) or (
                clip["sha256"] != previous.get("sha256") or clip["duration"] != previous.get("duration")
            ):
                raise ValueError(f"{narrator}:{verse}: clip differs from existing manifest; {source_hint}")


def find_sources(source_dirs: list[Path]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            raise FileNotFoundError(f"{source_dir}: source directory does not exist")
        for narrator in NARRATORS:
            candidate = source_dir / f"{narrator}.mp3"
            if not candidate.is_file():
                continue
            if narrator in sources:
                raise ValueError(
                    f"{narrator}: found in both {sources[narrator]} and {candidate}; source is ambiguous"
                )
            sources[narrator] = candidate
    if not sources:
        raise FileNotFoundError(
            f"no <narrator>.mp3 sources found in {', '.join(map(str, source_dirs))}"
        )
    return sources


def cut_audio(source: Path, target: Path, begin: Decimal, end: Decimal) -> None:
    clip_begin = begin - Decimal("0.050")
    clip_end = end + Decimal("0.150")
    if clip_begin < 0:
        raise ValueError(f"{target}: cannot add leading margin")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
        "-ss", str(clip_begin), "-t", str(clip_end - clip_begin), "-vn", "-ac", "1", "-ar", "24000",
        "-c:a", "libmp3lame", "-b:a", "56k", "-map_metadata", "-1", str(target),
    ], check=True)


def cut_clips(narrator: str, source: Path, timings: dict, passage: dict = JOHN) -> None:
    for verse in passage["verses"]:
        cut_audio(source, audio_output(passage) / narrator / f"{verse}.mp3", *timings[narrator, verse])


def cut_continuous(narrator: str, source: Path, timings: dict, passage: dict = JOHN) -> None:
    first, last = passage["verses"][0], passage["verses"][-1]
    cut_audio(source, audio_output(passage) / narrator / f"{verse_span(passage)}.mp3",
              timings[narrator, first][0], timings[narrator, last][1])


def audio_duration(target: Path) -> Decimal:
    return Decimal(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target),
    ], capture_output=True, text=True, check=True).stdout.strip())


def clip_info(narrator: str, timings: dict, passage: dict = JOHN) -> list[dict]:
    narrator_dir = audio_output(passage) / narrator
    verses = []
    for verse in passage["verses"]:
        target = narrator_dir / f"{verse}.mp3"
        if not target.is_file():
            raise FileNotFoundError(
                f"{target}: missing; run with --source-dir containing {narrator}.mp3 first"
            )
        duration = audio_duration(target)
        begin, end = timings[narrator, verse]
        if duration < end - begin:
            raise ValueError(f"{target}: shorter than requested verse interval")
        verses.append({
            "path": f"{audio_url(passage)}/{narrator}/{verse}.mp3",
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "duration": float(duration),
        })
    return verses


def continuous_info(narrator: str, timings: dict, passage: dict = JOHN) -> dict:
    target = audio_output(passage) / narrator / f"{verse_span(passage)}.mp3"
    if not target.is_file():
        raise FileNotFoundError(f"{target}: missing; pass a --source-dir containing {narrator}.mp3")
    duration = audio_duration(target)
    first_begin = timings[narrator, passage["verses"][0]][0] - Decimal("0.050")
    intervals = [
        {"start": float(timings[narrator, verse][0] - first_begin),
         "end": float(timings[narrator, verse][1] - first_begin)}
        for verse in passage["verses"]
    ]
    if duration < timings[narrator, passage["verses"][-1]][1] - first_begin:
        raise ValueError(f"{target}: shorter than requested continuous interval")
    return {
        "path": f"{audio_url(passage)}/{narrator}/{verse_span(passage)}.mp3",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "duration": float(duration),
        "intervals": intervals,
    }


def validate_demos(demos: dict[str, dict]) -> None:
    for demo_id, demo in demos.items():
        if "kind" not in demo:
            raise ValueError(f"{demo_id}: demo definition has no kind")
        if demo["kind"] not in DEMO_SELECTIONS:
            raise ValueError(f"{demo_id}: unknown demo kind {demo['kind']!r}")
        if demo.get("passage") not in PASSAGES:
            raise ValueError(f"{demo_id}: unknown passage")


def build(source_dirs: list[Path], passage_id: str = "john1") -> dict[str, dict]:
    validate_demos(DEMOS)
    passage = PASSAGES[passage_id]
    demos = {key: demo for key, demo in DEMOS.items() if demo["passage"] == passage_id}
    timings, texts = source_data(passage)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    sources = find_sources(source_dirs)
    previous_clips = recorded_clips(passage)
    previous_continuous = recorded_continuous(passage)
    voice_narrators = {narrator for demo in demos.values() if demo["kind"] == "voices" for group in demo["rows"].values() for narrator in group}
    for narrator, source in sources.items():
        cut_clips(narrator, source, timings, passage)
        if narrator in voice_narrators:
            cut_continuous(narrator, source, timings, passage)

    clips_by_narrator = {narrator: clip_info(narrator, timings, passage) for narrator in NARRATORS}
    for narrator, clips in clips_by_narrator.items():
        if narrator not in sources:
            validate_reused_clips(narrator, clips, previous_clips[narrator], timings, passage)
    continuous_by_narrator = {narrator: continuous_info(narrator, timings, passage) for narrator in voice_narrators}
    for narrator, info in continuous_by_narrator.items():
        if narrator not in sources and info != previous_continuous.get(narrator):
            raise ValueError(f"{narrator}: continuous clip differs from existing manifest; pass a --source-dir containing {narrator}.mp3")

    manifests = {}
    for demo_id, demo in demos.items():
        kind = demo["kind"]
        selection = demo[DEMO_SELECTIONS[kind]]
        narrators_used = sorted({narrator for group in selection.values() for narrator in group})
        clips = {
            narrator: {
                "translation": NARRATORS[narrator]["translation"],
                "names": NARRATORS[narrator]["names"],
                "verses": clips_by_narrator[narrator],
            }
            for narrator in narrators_used
        }
        if kind == "voices":
            for narrator in narrators_used:
                clips[narrator]["continuous"] = continuous_by_narrator[narrator]
        translations_used = sorted({NARRATORS[narrator]["translation"] for narrator in narrators_used})
        data = {
            "title": demo["title"],
            "passages": {**passage, "chapters": {key: passage["chapters"][key] for key in translations_used}},
            "kind": kind,
            "clips": clips,
            "texts": {
                translation: [texts[translation, verse] for verse in passage["verses"]]
                for translation in translations_used
            },
        }
        if kind == "voices":
            data["rows"] = {
                lang: [{"narrator": narrator, "note": MUSIC_NOTES[lang][narrator != "bondarenko"]} for narrator in narrators]
                for lang, narrators in demo["rows"].items()
            }
        else:
            data["pairs"] = demo["pairs"]
        manifest = DEMOS_DIR / f"{demo_id}.json"
        DEMOS_DIR.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifests[demo_id] = data

    return manifests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path, action="append", required=True, dest="source_dirs",
        help="directory with full-chapter MP3s for the selected passage named <narrator>.mp3; may be given more than once",
    )
    parser.add_argument("--passage", choices=PASSAGES, default="john1", help="passage whose demos to regenerate")
    args = parser.parse_args()
    build(args.source_dirs, args.passage)
