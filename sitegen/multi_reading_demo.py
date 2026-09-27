"""Validated, server-rendered Multi Reading article demo."""

from __future__ import annotations

import html
import hashlib
import json
import math
import re
from pathlib import Path

from .errors import BuildError

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "content/bible-garden/demos/multi-reading.json"
MARKER_ID = "multi-reading"
PLACEHOLDER = '<div data-demo-placeholder="multi-reading"></div>'
MARKER_RE = re.compile(r"^<!-- demo: ([a-z0-9]+(?:-[a-z0-9]+)*) -->$")
INTENT_RE = re.compile(r"<!--\s*(?:demo|dmeo|demmo)\b", re.IGNORECASE)
PAIRS = {"en": ["bsb_souer", "prudovsky"], "ru": ["prozorovsky", "bsb_souer"], "uk": ["kozlov_uk", "bsb_souer"]}
TRANSLATIONS = {"bsb_souer": "bsb", "prozorovsky": "bti", "prudovsky": "syn", "kozlov_uk": "ubh"}
TEXT_LANG = {"bsb": "en", "bti": "ru", "syn": "ru", "ubh": "uk"}


def annotate_demo_marker(body: str, source: Path, site: str, body_start_line: int = 1) -> tuple[str, bool]:
    from .content import _fenced_flags

    lines = body.splitlines()
    fenced = _fenced_flags(lines)
    found = False
    for index, line in enumerate(lines):
        if fenced[index] or not INTENT_RE.search(line):
            continue
        match = MARKER_RE.fullmatch(line)
        if not match:
            raise BuildError(f"{source}:{body_start_line + index}: expected <!-- demo: multi-reading -->")
        if site != "bible-garden" or match.group(1) != MARKER_ID:
            raise BuildError(f"{source}:{body_start_line + index}: unknown demo {match.group(1)!r} for {site}")
        if found:
            raise BuildError(f"{source}:{body_start_line + index}: duplicate Multi Reading demo marker")
        lines[index] = PLACEHOLDER
        found = True
    return "\n".join(lines) + ("\n" if body.endswith("\n") else ""), found


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def validate_demo(data: object, path: Path = DATA_PATH, static_root: Path = ROOT / "static/bible-garden") -> dict:
    def fail(message: str) -> None:
        raise BuildError(f"{path}: {message}")

    if not isinstance(data, dict) or set(data) != {"passages", "pairs", "clips", "texts"} or data["passages"] != "John 1:1–5":
        fail("expected John 1:1–5 demo data")
    if data["pairs"] != PAIRS or not isinstance(data["clips"], dict) or set(data["clips"]) != set(TRANSLATIONS):
        fail("invalid language pairs or narrator set")
    if not isinstance(data["texts"], dict) or set(data["texts"]) != set(TRANSLATIONS.values()):
        fail("invalid translation set")
    for translation, verses in data["texts"].items():
        if not isinstance(verses, list) or len(verses) != 5 or any(not isinstance(text, str) or not text.strip() for text in verses):
            fail(f"{translation}: expected five nonempty verse texts")
    for narrator, clip in data["clips"].items():
        if not isinstance(clip, dict) or set(clip) != {"path", "sha256", "duration", "translation", "names", "verses"}:
            fail(f"{narrator}: invalid clip fields")
        expected_path = f"/audio/demo/{narrator}.mp3"
        if clip["path"] != expected_path or clip["translation"] != TRANSLATIONS[narrator]:
            fail(f"{narrator}: invalid clip path or translation")
        clip_file = static_root / expected_path.lstrip("/")
        if not clip_file.is_file():
            fail(f"{narrator}: missing clip {expected_path}")
        if not isinstance(clip["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", clip["sha256"]):
            fail(f"{narrator}: invalid clip SHA-256")
        if hashlib.sha256(clip_file.read_bytes()).hexdigest() != clip["sha256"]:
            fail(f"{narrator}: clip checksum mismatch")
        duration = clip["duration"]
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
            fail(f"{narrator}: invalid clip duration")
        names = clip["names"]
        if not isinstance(names, dict) or set(names) != set(PAIRS) or any(
            not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(name, str) or not name.strip() for name in pair)
            for pair in names.values()
        ):
            fail(f"{narrator}: invalid localized translation or narrator names")
        verses = clip["verses"]
        if not isinstance(verses, list) or len(verses) != 5:
            fail(f"{narrator}: expected five verse timings")
        previous_end = 0
        for index, pair in enumerate(verses, 1):
            if not isinstance(pair, list) or len(pair) != 2 or any(type(value) not in (int, float) or not math.isfinite(value) for value in pair):
                fail(f"{narrator}: verse {index} has invalid timing")
            begin, end = pair
            if begin < previous_end or begin >= end or end > duration:
                fail(f"{narrator}: verse {index} timing outside clip length or overlaps")
            previous_end = end
    return data


def load_demo(path: Path = DATA_PATH, static_root: Path = ROOT / "static/bible-garden") -> dict:
    if not path.is_file():
        raise BuildError(f"{path}: missing Multi Reading demo data; run tools/build_demo_audio.py")
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (OSError, ValueError) as error:
        raise BuildError(f"{path}: invalid Multi Reading demo JSON: {error}") from error
    return validate_demo(data, path, static_root)


def render_demo(data: dict, lang: str, strings: object) -> str:
    required = {"title", "play", "pause", "play_again", "error", "manual_audio"}
    if lang not in PAIRS or not isinstance(strings, dict) or set(strings) != required or any(
        not isinstance(value, str) or not value.strip() for value in strings.values()
    ):
        raise BuildError(f"Multi Reading demo: missing or invalid translation for {lang}")
    first, second = (data["clips"][narrator] for narrator in PAIRS[lang])
    first_lang = TEXT_LANG[first["translation"]]
    second_lang = TEXT_LANG[second["translation"]]
    esc = html.escape
    out = [f'<section class="multi-reading-demo" data-multi-reading-demo data-play="{esc(strings["play"], quote=True)}"'
           f' data-pause="{esc(strings["pause"], quote=True)}" data-play-again="{esc(strings["play_again"], quote=True)}"'
           f' data-error="{esc(strings["error"], quote=True)}" aria-labelledby="multi-reading-demo-title">',
           f'<h3 id="multi-reading-demo-title">{esc(strings["title"])}</h3>',
           '<div class="multi-reading-legend">']
    for key, clip in (("a", first), ("b", second)):
        translation, narrator = clip["names"][lang]
        out.append(f'<p><span class="multi-reading-key multi-reading-key-{key.upper()}">{key.upper()}</span> '
                   f'{esc(translation)} · {esc(narrator)}</p>')
    out.append('</div><div class="multi-reading-controls" hidden>'
               f'<button type="button" class="multi-reading-toggle">{esc(strings["play"])}</button>'
               '<p class="multi-reading-error" role="alert" hidden></p></div>')
    out.append('<ol class="multi-reading-verses">')
    for index in range(5):
        out.append(f'<li data-verse="{index + 1}"><span class="multi-reading-number">{index + 1}</span>'
                   f'<div class="multi-reading-lines"><p class="multi-reading-line" data-step="a" lang="{first_lang}">{esc(data["texts"][first["translation"]][index])}</p>'
                   f'<p class="multi-reading-line multi-reading-secondary" data-step="b" lang="{second_lang}">{esc(data["texts"][second["translation"]][index])}</p></div></li>')
    out.append('</ol>')
    out.append(f'<p class="multi-reading-manual-label">{esc(strings["manual_audio"])}</p><div class="multi-reading-manual">')
    for key, clip in (("a", first), ("b", second)):
        translation, narrator = clip["names"][lang]
        timing = esc(json.dumps(clip["verses"], separators=(",", ":")), quote=True)
        name = f"{translation} · {narrator}"
        out.append(f'<div><span>{esc(name)}</span>'
                   f'<audio controls preload="none" aria-label="{esc(name, quote=True)}" data-audio="{key}" data-verses="{timing}" src="{esc(clip["path"], quote=True)}"></audio></div>')
    out.append('</div></section>')
    return "\n".join(out)
