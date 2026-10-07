"""Validated server-rendered Lampada demo; no live app services or private input."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

from urllib.parse import urlsplit
from .templates import make_environment

from .errors import BuildError
from .demo_markers import unique_keys, reject_constant

ROOT = Path(__file__).resolve().parent.parent
DEMOS_DIR = ROOT / 'content/lampada/demos'
STATIC_ROOT = ROOT / 'static/lampada'
LANGS = {'en', 'ru', 'uk'}
STRING_KEYS = set((
    'journal favorites settings lit keep_flame start title remaining goal finish_prayer music '
    'question quote answer edit listen pause resume previous_question next_question save_quote '
    'saved_quote previous_quote next_quote sheet_question placeholder voice_hint mic cancel '
    'confirm_cancel save reflect_before reflect_placeholder reflect_save reflect_finish reflect_return '
    'prayer_saved demo_title intro privacy available sample restart close no_js audio_error saved_demo '
    'audio_credit translation_credit notice_title licenses static_caption report_question report_scripture'
).split())
FONTS = ('Spectral_300Light', 'Spectral_300Light_Italic', 'Spectral_400Regular',
         'HankenGrotesk_400Regular', 'HankenGrotesk_500Medium', 'HankenGrotesk_600SemiBold',
         'JetBrainsMono_400Regular')


def validate_strings(lang: str, strings: object) -> dict:
    if lang not in LANGS or not isinstance(strings, dict):
        raise BuildError(f'Prayer demo: missing or invalid translation for {lang}')
    required = STRING_KEYS | {'greetings', 'week'}
    allowed = required | {'audio_unavailable', 'license_label'}
    if not required <= set(strings) or not set(strings) <= allowed:
        raise BuildError(f'Prayer demo: invalid translation keys for {lang}')
    for key in set(strings) - {'greetings', 'week'}:
        if not isinstance(strings[key], str) or not strings[key].strip():
            raise BuildError(f'Prayer demo: invalid {lang}.{key}')
    for key, expected in [('greetings', {'night', 'morning', 'afternoon', 'evening'}),
                          ('week', {'one', 'few', 'many', 'other'})]:
        value = strings[key]
        if not isinstance(value, dict) or set(value) != expected or any(not isinstance(v, str) or not v.strip() for v in value.values()):
            raise BuildError(f'Prayer demo: invalid {lang}.{key}')
    if any('{count}' not in v for v in strings['week'].values()):
        raise BuildError(f'Prayer demo: missing count placeholder for {lang}')
    return strings


def week_label(lang: str, strings: dict, count: int) -> str:
    if count == 0:
        return ''
    if lang == 'en':
        category = 'one' if count == 1 else 'other'
    else:
        category = ('one' if count % 10 == 1 and count % 100 != 11 else
                    'few' if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else 'many')
    return strings['week'][category].replace('{count}', str(count))



def validate_demo(data: object, path: Path, static_root: Path = STATIC_ROOT) -> dict:
    def fail(message: str) -> None:
        raise BuildError(f'{path}: {message}')

    def fields(value: object, expected: set[str], label: str) -> None:
        if not isinstance(value, dict) or set(value) != expected:
            fail(f'invalid {label} fields')

    def text(value: object, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            fail(f'missing {label}')

    fields(data, {'kind', 'source_commit', 'timer', 'week', 'locales'}, 'demo')
    if data['kind'] != 'prayer-session' or not isinstance(data['source_commit'], str) or not re.fullmatch(r'[0-9a-f]{7,40}', data['source_commit']):
        fail('invalid kind or source commit')
    fields(data['timer'], {'total', 'remaining'}, 'timer')
    total, remaining = data['timer']['total'], data['timer']['remaining']
    if type(total) is not int or type(remaining) is not int or not 0 < remaining <= total <= 3600:
        fail('invalid timer')
    week = data['week']
    if not isinstance(week, list) or len(week) != 7 or any(type(v) is not bool for v in week):
        fail('expected seven boolean week days')
    fields(data['locales'], LANGS, 'locales')
    for lang, value in data['locales'].items():
        fields(value, {'goal', 'questions', 'sample_answer', 'reflection', 'scripture', 'audio'}, lang)
        for key in ('goal', 'sample_answer', 'reflection'):
            text(value[key], f'{lang}.{key}')
        if not isinstance(value['questions'], list) or len(value['questions']) != 3:
            fail(f'{lang}: expected first, alternate and next question')
        for question in value['questions']:
            text(question, f'{lang}.question')
        scripture = value['scripture']
        fields(scripture, {'text', 'reference', 'translation', 'translation_name', 'book', 'chapter', 'verse', 'source', 'verified_on'}, 'scripture')
        for key in ('text', 'reference', 'translation_name', 'source', 'verified_on'):
            text(scripture[key], f'{lang}.scripture.{key}')
        translation = scripture['translation']
        if not isinstance(translation, str) or not re.fullmatch(r'[a-z0-9]+', translation):
            fail(f'{lang}: invalid translation alias')
        for key in ('book', 'chapter', 'verse'):
            if type(scripture[key]) is not int or scripture[key] <= 0:
                fail(f'{lang}: invalid Scripture {key}')
        if scripture['source'] != f'text/{translation}.json' or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', scripture['verified_on']):
            fail(f'{lang}: invalid Scripture provenance')
        try:
            dt.date.fromisoformat(scripture['verified_on'])
        except ValueError:
            fail(f'{lang}: invalid verification date')
        audio = value['audio']
        if not isinstance(audio, dict) or audio.get('status') not in {'available', 'unavailable'}:
            fail(f'{lang}: missing explicit audio availability')
        if audio['status'] == 'unavailable':
            fields(audio, {'status', 'reason'}, 'unavailable audio')
            text(audio['reason'], f'{lang}.audio.reason')
            continue
        fields(audio, {'status', 'path', 'sha256', 'duration', 'source_file', 'source_sha256', 'begin', 'end', 'narrator', 'license', 'license_url', 'research', 'changes'}, 'audio')
        if lang == 'ru':
            fail('Russian audio is disabled by the owner decision of 2026-10-07')
        expected_path = audio['path']
        if not isinstance(expected_path, str) or not re.fullmatch(r'/assets/audio/prayer-session/[a-z0-9-]+\.mp3', expected_path):
            fail(f'{lang}: invalid clip path')
        for key in ('narrator', 'license', 'research', 'changes'):
            text(audio[key], f'{lang}.audio.{key}')
        if not isinstance(audio['license_url'], str):
            fail(f'{lang}: invalid rights URL')
        url = urlsplit(audio['license_url'])
        if url.scheme not in {'http', 'https'} or not url.netloc or url.username or url.password:
            fail(f'{lang}: invalid rights URL')
        source_pattern = rf'audio/{translation}/[a-z0-9_]+/mp3/{scripture["book"]:02}/{scripture["chapter"]:02}\.mp3'
        if not isinstance(audio['source_file'], str) or not re.fullmatch(source_pattern, audio['source_file']):
            fail(f'{lang}: text and recording translations differ')
        for key in ('sha256', 'source_sha256'):
            if not isinstance(audio[key], str) or not re.fullmatch(r'[0-9a-f]{64}', audio[key]):
                fail(f'{lang}: invalid {key}')
        for key in ('duration', 'begin', 'end'):
            n = audio[key]
            if type(n) not in (int, float) or not math.isfinite(n) or n < 0:
                fail(f'{lang}: invalid {key}')
        if audio['duration'] <= 0 or audio['end'] <= audio['begin'] or abs(audio['duration'] - (audio['end'] - audio['begin'])) > .25:
            fail(f'{lang}: invalid clip duration')
        clip = static_root / expected_path.lstrip('/')
        if not clip.is_file() or hashlib.sha256(clip.read_bytes()).hexdigest() != audio['sha256']:
            fail(f'{lang}: missing clip or checksum mismatch')
    font_dir = static_root / 'assets/fonts'
    expected_fonts = {f'{font}.woff2' for font in FONTS}
    if not font_dir.is_dir() or {p.name for p in font_dir.iterdir()} != expected_fonts:
        fail('missing or unused font faces')
    for font in FONTS:
        font_file = font_dir / f'{font}.woff2'
        if not font_file.is_file() or font_file.stat().st_size < 48 or font_file.read_bytes()[:4] != b'wOF2':
            fail(f'invalid WOFF2 font {font}')
    for notice in ('spectral-OFL.txt', 'hanken-grotesk-OFL.txt', 'jetbrains-mono-OFL.txt', 'lampada-MIT.txt', 'lucide.txt', 'prayer-audio.txt', 'index.html'):
        if not (static_root / f'assets/licenses/{notice}').is_file():
            fail(f'missing license notice {notice}')
    return data


def load_demo(demo_id: str = 'prayer-session', demos_dir: Path = DEMOS_DIR, static_root: Path = STATIC_ROOT) -> dict:
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', demo_id):
        raise BuildError(f'invalid prayer demo id {demo_id!r}')
    path = demos_dir / f'{demo_id}.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_keys, parse_constant=reject_constant)
    except (OSError, ValueError) as error:
        raise BuildError(f'{path}: invalid or missing prayer demo JSON: {error}') from error
    return validate_demo(data, path, static_root)


def render_demo(data: dict, lang: str, strings: object) -> str:
    strings = validate_strings(lang, strings)
    locale = data['locales'][lang]
    credit_key = 'license_label' if locale['audio']['status'] == 'available' else 'audio_unavailable'
    if credit_key not in strings:
        raise BuildError(f'Prayer demo: missing {lang}.{credit_key}')
    remaining = data['timer']['remaining']
    return make_environment('lampada').get_template('prayer-session-demo.html').render(
        d=locale, t=strings, lang=lang, prefix=f'pd-prayer-session-{lang}', week=data['week'],
        week_label=week_label(lang, strings, sum(data['week'])),
        timer=f'{remaining // 60:02}:{remaining % 60:02}', ring_offset=440 * (1 - remaining / data['timer']['total']),
    )
