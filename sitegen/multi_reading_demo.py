"""Validated, server-rendered passage-based article audio demos.

A demo marker `<!-- demo: <id> -->` loads
`content/bible-garden/demos/<id>.json`. Demos share the player markup, CSS and
JS. Verse clips live under
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
LANGS = {"en", "ru", "uk"}
# Language of each translation's text, for the verse line's `lang` attribute.
# Fixed per translation regardless of which demo(s) use it.
TEXT_LANG = {"bsb": "en", "bti": "ru", "syn": "ru", "ubh": "uk", "webus": "en", "webbe": "en", "npu": "uk"}


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

    if not isinstance(data, dict) or data.get("kind") not in {"multi-reading", "voices"}:
        fail("expected audio demo data")
    kind = data["kind"]
    expected_fields = {"kind", "title", "passages", "clips", "texts", "pairs" if kind == "multi-reading" else "rows"}
    if set(data) != expected_fields:
        fail("invalid demo fields")

    passage = data["passages"]
    if not isinstance(passage, dict) or set(passage) != {"book", "chapters", "verses", "audio_dir"}:
        fail("invalid passage fields")
    if type(passage["book"]) is not int or not 1 <= passage["book"] <= 66:
        fail("invalid passage book")
    chapters = passage["chapters"]
    if not isinstance(chapters, dict) or not chapters or any(
        key not in TEXT_LANG or type(value) is not int or not 1 <= value <= 150
        for key, value in chapters.items()
    ):
        fail("invalid passage chapters")
    numbers = passage["verses"]
    if (not isinstance(numbers, list) or not numbers or any(type(number) is not int or number < 1 for number in numbers)
            or numbers != list(range(numbers[0], numbers[-1] + 1))):
        fail("invalid passage verses")
    count = len(numbers)
    audio_dir = passage["audio_dir"]
    if not isinstance(audio_dir, str) or (audio_dir and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", audio_dir)):
        fail("invalid passage audio directory")
    audio_prefix = "/audio/demo" + ("/" + audio_dir if audio_dir else "")

    title = data["title"]
    if not isinstance(title, dict) or not title or not set(title) <= LANGS or any(
        not isinstance(value, str) or not value.strip() for value in title.values()
    ):
        fail("invalid localized title")

    clips = data["clips"]
    if not isinstance(clips, dict) or not clips:
        fail("invalid narrator set")

    if kind == "multi-reading":
        pairs = data["pairs"]
        if not isinstance(pairs, dict) or set(pairs) != set(title):
            fail("invalid language pairs")
        for lang, pair in pairs.items():
            if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1] or any(
                not isinstance(narrator, str) or narrator not in clips for narrator in pair
            ):
                fail(f"{lang}: invalid narrator pair")
        used = {narrator for pair in pairs.values() for narrator in pair}
    else:
        rows = data["rows"]
        if not isinstance(rows, dict) or set(rows) != set(title):
            fail("invalid language rows")
        used = set()
        for lang, entries in rows.items():
            if not isinstance(entries, list) or not entries:
                fail(f"{lang}: invalid narrator rows")
            seen = set()
            for row in entries:
                if not isinstance(row, dict) or set(row) != {"narrator", "note"}:
                    fail(f"{lang}: invalid narrator row")
                narrator, note = row["narrator"], row["note"]
                if not isinstance(narrator, str) or narrator not in clips or narrator in seen or not isinstance(note, str) or not note.strip():
                    fail(f"{lang}: invalid narrator row")
                seen.add(narrator)
                used.add(narrator)
    if used != set(clips):
        fail("clips must match the narrators used in the demo")

    texts = data["texts"]
    if not isinstance(texts, dict):
        fail("invalid translation set")

    translations = set()
    for narrator, clip in clips.items():
        clip_fields = {"translation", "names", "verses"} | ({"continuous"} if kind == "voices" else set())
        if not isinstance(clip, dict) or set(clip) != clip_fields:
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
        if not isinstance(verses, list) or len(verses) != count:
            fail(f"{narrator}: expected {count} verse clips")
        for index, verse in zip(numbers, verses):
            if not isinstance(verse, dict) or set(verse) != {"path", "sha256", "duration"}:
                fail(f"{narrator}: verse {index} has invalid clip fields")
            expected_path = f"{audio_prefix}/{narrator}/{index}.mp3"
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
        if kind == "voices":
            continuous = clip["continuous"]
            if not isinstance(continuous, dict) or set(continuous) != {"path", "sha256", "duration", "intervals"}:
                fail(f"{narrator}: invalid continuous clip fields")
            expected_path = f"{audio_prefix}/{narrator}/{numbers[0]}-{numbers[-1]}.mp3"
            if continuous["path"] != expected_path:
                fail(f"{narrator}: invalid continuous clip path")
            clip_file = static_root / expected_path.lstrip("/")
            if not clip_file.is_file():
                fail(f"{narrator}: missing continuous clip {expected_path}")
            if not isinstance(continuous["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", continuous["sha256"]):
                fail(f"{narrator}: invalid continuous clip SHA-256")
            if hashlib.sha256(clip_file.read_bytes()).hexdigest() != continuous["sha256"]:
                fail(f"{narrator}: continuous clip checksum mismatch")
            duration = continuous["duration"]
            if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
                fail(f"{narrator}: invalid continuous clip duration")
            intervals = continuous["intervals"]
            if not isinstance(intervals, list) or len(intervals) != count:
                fail(f"{narrator}: expected {count} verse intervals")
            previous_end = 0
            for interval in intervals:
                if not isinstance(interval, dict) or set(interval) != {"start", "end"}:
                    fail(f"{narrator}: invalid verse interval")
                start, end = interval["start"], interval["end"]
                if (type(start) not in (int, float) or type(end) not in (int, float)
                        or not math.isfinite(start) or not math.isfinite(end)
                        or start < previous_end or end <= start or end > duration):
                    fail(f"{narrator}: invalid verse interval")
                previous_end = end

    if set(texts) != translations or set(chapters) != translations:
        fail("invalid translation set")
    for translation, verses in texts.items():
        if not isinstance(verses, list) or len(verses) != count or any(not isinstance(text, str) or not text.strip() for text in verses):
            fail(f"{translation}: expected {count} nonempty verse texts")
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


# Highlighting alone is silent for screen readers; JS announces the current verse here.
STATUS = '<p class="sr-only" data-demo-status aria-live="polite"></p>'


def render_demo(data: dict, lang: str, strings: object) -> str:
    required = {"play", "pause", "play_again", "error", "verse"}
    if lang not in LANGS or not isinstance(strings, dict) or set(strings) != required or any(
        not isinstance(value, str) or not value.strip() for value in strings.values()
    ):
        raise BuildError(f"Multi Reading demo: missing or invalid translation for {lang}")
    if lang not in data["title"]:
        raise BuildError(f"Audio demo: no rows for language {lang}")
    if data["kind"] == "voices":
        return _render_voices(data, lang, strings)
    first, second = (data["clips"][narrator] for narrator in data["pairs"][lang])
    first_lang = TEXT_LANG[first["translation"]]
    second_lang = TEXT_LANG[second["translation"]]
    esc = html.escape
    clip_paths = [clip["verses"][index]["path"] for index in range(len(data["passages"]["verses"])) for clip in (first, second)]
    clip_data = esc(json.dumps(clip_paths, separators=(",", ":")), quote=True)
    out = [f'<section class="multi-reading-demo" data-multi-reading-demo data-kind="multi-reading" data-play="{esc(strings["play"], quote=True)}"'
           f' data-pause="{esc(strings["pause"], quote=True)}" data-play-again="{esc(strings["play_again"], quote=True)}"'
           f' data-error="{esc(strings["error"], quote=True)}" data-verse-label="{esc(strings["verse"], quote=True)}"'
           f' data-clips="{clip_data}" aria-labelledby="multi-reading-demo-title">',
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
    out.append(STATUS)
    out.append('<ol class="multi-reading-verses">')
    for index, number in enumerate(data["passages"]["verses"]):
        out.append(f'<li data-verse="{number}"><span class="multi-reading-number">{number}</span>'
                   f'<div class="multi-reading-lines"><p class="multi-reading-line" data-step="a" lang="{first_lang}">{esc(data["texts"][first["translation"]][index])}</p>'
                   f'<p class="multi-reading-line multi-reading-secondary" data-step="b" lang="{second_lang}">{esc(data["texts"][second["translation"]][index])}</p></div></li>')
    first_path = esc(first["verses"][0]["path"], quote=True)
    out.append(f'</ol><audio data-demo-player preload="none" src="{first_path}"></audio></section>')
    return "\n".join(out)


def _render_voices(data: dict, lang: str, strings: dict) -> str:
    esc = html.escape
    out = [f'<section class="multi-reading-demo voices-demo" data-multi-reading-demo data-kind="voices"'
           f' data-play="{esc(strings["play"], quote=True)}" data-pause="{esc(strings["pause"], quote=True)}"'
           f' data-play-again="{esc(strings["play_again"], quote=True)}" data-error="{esc(strings["error"], quote=True)}"'
           f' data-verse-label="{esc(strings["verse"], quote=True)}" aria-labelledby="multi-reading-demo-title">',
           f'<h3 id="multi-reading-demo-title">{esc(data["title"][lang])}</h3>',
           '<div class="voices-rows">']
    for row in data["rows"][lang]:
        clip = data["clips"][row["narrator"]]
        translation, narrator = clip["names"][lang]
        label = f"{translation} · {narrator}" if narrator else translation
        continuous = clip["continuous"]
        intervals = esc(json.dumps(continuous["intervals"], separators=(",", ":")), quote=True)
        button_label = esc(f'{strings["play"]}: {label}', quote=True)
        out.append(f'<div class="voices-row" data-demo-track data-clips="{esc(json.dumps([continuous["path"]]), quote=True)}"'
                   f' data-intervals="{intervals}" data-label="{esc(label, quote=True)}">'
                   '<div class="voices-row-heading">'
                   f'<div class="voices-row-meta"><h4>{esc(label)}</h4><p class="voices-note">{esc(row["note"])}</p></div>'
                   '<div class="multi-reading-controls" hidden>'
                   f'<button type="button" class="multi-reading-toggle" aria-label="{button_label}">{esc(strings["play"])}</button>'
                   '<p class="multi-reading-error" role="alert" hidden></p></div></div>'
                   f'<p class="voices-passage" data-voice-passage lang="{TEXT_LANG[clip["translation"]]}">')
        for index, verse in zip(data["passages"]["verses"], data["texts"][clip["translation"]]):
            out.append(f'<span data-verse="{index}"><sup>{index}</sup> {esc(verse)}</span>')
        out.append('</p></div>')
    out.append('</div>')
    out.append(STATUS)
    first_narrator = data["rows"][lang][0]["narrator"]
    first_path = esc(data["clips"][first_narrator]["continuous"]["path"], quote=True)
    out.append(f'<audio data-demo-player preload="none" src="{first_path}"></audio></section>')
    return "\n".join(out)
