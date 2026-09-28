"""Validated, server-rendered Multi Reading article demos.

A demo marker `<!-- demo: <id> -->` loads
`content/bible-garden/demos/<id>.json`. Every demo plays John 1:1-5 verse by
verse in two voices (multi-reading: the same passage in two languages;
translation-compare: two translations of the same language), sharing the
generic player markup, CSS and JS. Verse clips live under
`static/bible-garden/audio/demo/<narrator>/<verse>.mp3` and are shared
between demos.
"""

from __future__ import annotations

import html
import hashlib
import json
import math
import re
from pathlib import Path

from .errors import BuildError

ROOT = Path(__file__).resolve().parent.parent
DEMOS_DIR = ROOT / "content/bible-garden/demos"
MARKER_RE = re.compile(r"^<!-- demo: ([a-z0-9]+(?:-[a-z0-9]+)*) -->$")
INTENT_RE = re.compile(r"<!--\s*(?:demo|dmeo|demmo)\b", re.IGNORECASE)
PASSAGE = "John 1:1–5"
LANGS = {"en", "ru", "uk"}
# Language of each translation's text, for the verse line's `lang` attribute.
# Fixed per translation regardless of which demo(s) use it.
TEXT_LANG = {"bsb": "en", "bti": "ru", "syn": "ru", "ubh": "uk", "webus": "en", "npu": "uk"}


def placeholder_for(demo_id: str) -> str:
    return f'<div data-demo-placeholder="{demo_id}"></div>'


def annotate_demo_marker(
    body: str, source: Path, site: str, body_start_line: int = 1, demos_dir: Path = DEMOS_DIR
) -> tuple[str, str | None]:
    from .content import _fenced_flags

    lines = body.splitlines()
    fenced = _fenced_flags(lines)
    found_id: str | None = None
    for index, line in enumerate(lines):
        if fenced[index] or not INTENT_RE.search(line):
            continue
        match = MARKER_RE.fullmatch(line)
        if not match:
            raise BuildError(f"{source}:{body_start_line + index}: expected <!-- demo: <id> -->")
        demo_id = match.group(1)
        if site != "bible-garden" or not (demos_dir / f"{demo_id}.json").is_file():
            raise BuildError(f"{source}:{body_start_line + index}: unknown demo {demo_id!r} for {site}")
        if found_id is not None:
            raise BuildError(f"{source}:{body_start_line + index}: duplicate demo marker")
        lines[index] = placeholder_for(demo_id)
        found_id = demo_id
    return "\n".join(lines) + ("\n" if body.endswith("\n") else ""), found_id


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def validate_demo(data: object, demo_id: str, path: Path, static_root: Path = ROOT / "static/bible-garden") -> dict:
    def fail(message: str) -> None:
        raise BuildError(f"{path}: {message}")

    if not isinstance(data, dict) or set(data) != {"title", "passages", "pairs", "clips", "texts"} or data.get("passages") != PASSAGE:
        fail("expected John 1:1–5 demo data")

    title = data["title"]
    if not isinstance(title, dict) or set(title) != LANGS or any(
        not isinstance(value, str) or not value.strip() for value in title.values()
    ):
        fail("invalid localized title")

    clips = data["clips"]
    if not isinstance(clips, dict) or not clips:
        fail("invalid narrator set")

    pairs = data["pairs"]
    if not isinstance(pairs, dict) or set(pairs) != LANGS:
        fail("invalid language pairs")
    for lang, pair in pairs.items():
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1] or any(
            not isinstance(narrator, str) or narrator not in clips for narrator in pair
        ):
            fail(f"{lang}: invalid narrator pair")
    if {narrator for pair in pairs.values() for narrator in pair} != set(clips):
        fail("clips must match the narrators used in pairs")

    texts = data["texts"]
    if not isinstance(texts, dict):
        fail("invalid translation set")

    translations = set()
    for narrator, clip in clips.items():
        if not isinstance(clip, dict) or set(clip) != {"translation", "names", "verses"}:
            fail(f"{narrator}: invalid clip fields")
        translation = clip["translation"]
        if not isinstance(translation, str) or translation not in TEXT_LANG:
            fail(f"{narrator}: unknown translation {translation!r}")
        translations.add(translation)
        names = clip["names"]
        if not isinstance(names, dict) or set(names) != LANGS:
            fail(f"{narrator}: invalid localized translation or narrator names")
        for localized in names.values():
            if not isinstance(localized, list) or len(localized) != 2:
                fail(f"{narrator}: invalid localized translation or narrator names")
            translation_name, narrator_name = localized
            if not isinstance(translation_name, str) or not translation_name.strip():
                fail(f"{narrator}: invalid localized translation or narrator names")
            if narrator_name is not None and (not isinstance(narrator_name, str) or not narrator_name.strip()):
                fail(f"{narrator}: invalid localized translation or narrator names")
        verses = clip["verses"]
        if not isinstance(verses, list) or len(verses) != 5:
            fail(f"{narrator}: expected five verse clips")
        for index, verse in enumerate(verses, 1):
            if not isinstance(verse, dict) or set(verse) != {"path", "sha256", "duration"}:
                fail(f"{narrator}: verse {index} has invalid clip fields")
            expected_path = f"/audio/demo/{narrator}/{index}.mp3"
            if verse["path"] != expected_path:
                fail(f"{narrator}: verse {index} has invalid clip path")
            clip_file = static_root / expected_path.lstrip("/")
            if not clip_file.is_file():
                fail(f"{narrator}: verse {index} missing clip {expected_path}")
            if not isinstance(verse["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", verse["sha256"]):
                fail(f"{narrator}: verse {index} has invalid clip SHA-256")
            if hashlib.sha256(clip_file.read_bytes()).hexdigest() != verse["sha256"]:
                fail(f"{narrator}: verse {index} clip checksum mismatch")
            duration = verse["duration"]
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
                fail(f"{narrator}: verse {index} has invalid clip duration")

    if set(texts) != translations:
        fail("invalid translation set")
    for translation, verses in texts.items():
        if not isinstance(verses, list) or len(verses) != 5 or any(not isinstance(text, str) or not text.strip() for text in verses):
            fail(f"{translation}: expected five nonempty verse texts")
    return data


def load_demo(demo_id: str, demos_dir: Path = DEMOS_DIR, static_root: Path = ROOT / "static/bible-garden") -> dict:
    path = demos_dir / f"{demo_id}.json"
    if not path.is_file():
        raise BuildError(f"{path}: missing demo data; run tools/build_demo_audio.py")
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (OSError, ValueError) as error:
        raise BuildError(f"{path}: invalid demo JSON: {error}") from error
    return validate_demo(data, demo_id, path, static_root)


def render_demo(data: dict, lang: str, strings: object) -> str:
    required = {"play", "pause", "play_again", "error"}
    if lang not in LANGS or not isinstance(strings, dict) or set(strings) != required or any(
        not isinstance(value, str) or not value.strip() for value in strings.values()
    ):
        raise BuildError(f"Multi Reading demo: missing or invalid translation for {lang}")
    first, second = (data["clips"][narrator] for narrator in data["pairs"][lang])
    first_lang = TEXT_LANG[first["translation"]]
    second_lang = TEXT_LANG[second["translation"]]
    esc = html.escape
    clip_paths = [clip["verses"][index]["path"] for index in range(5) for clip in (first, second)]
    clip_data = esc(json.dumps(clip_paths, separators=(",", ":")), quote=True)
    out = [f'<section class="multi-reading-demo" data-multi-reading-demo data-play="{esc(strings["play"], quote=True)}"'
           f' data-pause="{esc(strings["pause"], quote=True)}" data-play-again="{esc(strings["play_again"], quote=True)}"'
           f' data-error="{esc(strings["error"], quote=True)}" data-clips="{clip_data}" aria-labelledby="multi-reading-demo-title">',
           f'<h3 id="multi-reading-demo-title">{esc(data["title"][lang])}</h3>',
           '<div class="multi-reading-legend">']
    for key, clip in (("a", first), ("b", second)):
        translation, narrator = clip["names"][lang]
        label = f"{esc(translation)} · {esc(narrator)}" if narrator else esc(translation)
        out.append(f'<p><span class="multi-reading-key multi-reading-key-{key.upper()}">{key.upper()}</span> '
                   f'{label}</p>')
    out.append('</div><div class="multi-reading-controls" hidden>'
               f'<button type="button" class="multi-reading-toggle">{esc(strings["play"])}</button>'
               '<p class="multi-reading-error" role="alert" hidden></p></div>')
    out.append('<ol class="multi-reading-verses">')
    for index in range(5):
        out.append(f'<li data-verse="{index + 1}"><span class="multi-reading-number">{index + 1}</span>'
                   f'<div class="multi-reading-lines"><p class="multi-reading-line" data-step="a" lang="{first_lang}">{esc(data["texts"][first["translation"]][index])}</p>'
                   f'<p class="multi-reading-line multi-reading-secondary" data-step="b" lang="{second_lang}">{esc(data["texts"][second["translation"]][index])}</p></div></li>')
    first_path = esc(first["verses"][0]["path"], quote=True)
    out.append(f'</ol><audio data-demo-player preload="none" src="{first_path}"></audio></section>')
    return "\n".join(out)
