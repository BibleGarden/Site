"""Validated server-rendered Lampada demo; no live app services or private input."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .errors import BuildError
from .multi_reading_demo import _unique_keys, _reject_constant

ROOT = Path(__file__).resolve().parent.parent
DEMOS_DIR = ROOT / 'content/lampada/demos'
STATIC_ROOT = ROOT / 'static/lampada'
LANGS = {'en', 'ru', 'uk'}
STRING_KEYS = set('greeting journal favorites settings lit start title remaining goal finish_prayer music question quote answer edit listen pause resume previous_question next_question save_quote saved_quote previous_quote next_quote sheet_question placeholder voice_hint mic cancel confirm_cancel save reflect_before reflect_placeholder reflect_save reflect_finish reflect_return prayer_saved demo_title intro privacy available sample restart close no_js audio_error audio_unavailable saved_demo audio_credit notice_title week license_label'.split())
FONTS = ('Spectral_300Light', 'Spectral_300Light_Italic', 'Spectral_400Regular', 'Spectral_600SemiBold', 'HankenGrotesk_400Regular', 'HankenGrotesk_500Medium', 'HankenGrotesk_600SemiBold', 'JetBrainsMono_400Regular', 'JetBrainsMono_500Medium')


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
    if data['kind'] != 'prayer-session' or not re.fullmatch(r'[0-9a-f]{7,40}', str(data['source_commit'])):
        fail('invalid kind or source commit')
    fields(data['timer'], {'total', 'remaining'}, 'timer')
    total, remaining = data['timer']['total'], data['timer']['remaining']
    if type(total) is not int or type(remaining) is not int or not 0 < remaining <= total <= 3600:
        fail('invalid timer')
    week = data['week']
    if not isinstance(week, list) or len(week) != 7 or any(type(v) is not bool for v in week) or sum(week) != 3 or not week[-1]:
        fail('expected a lit home with three days of prayer')
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
        translation, chapter = {'en': ('bsb', 118), 'ru': ('syn', 117), 'uk': ('ubh', 118)}[lang]
        if (scripture['translation'], scripture['book'], scripture['chapter'], scripture['verse']) != (translation, 19, chapter, 24):
            fail(f'{lang}: unexpected Scripture translation or reference')
        if scripture['source'] != f'text/{translation}.json' or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', scripture['verified_on']):
            fail(f'{lang}: invalid Scripture provenance')
        audio = value['audio']
        if not isinstance(audio, dict) or audio.get('status') not in {'available', 'unavailable'}:
            fail(f'{lang}: missing explicit audio availability')
        if audio['status'] == 'unavailable':
            fields(audio, {'status', 'reason'}, 'unavailable audio')
            text(audio['reason'], f'{lang}.audio.reason')
            if lang != 'ru':
                fail(f'{lang}: expected confirmed audio')
            continue
        fields(audio, {'status', 'path', 'sha256', 'duration', 'source_file', 'source_sha256', 'begin', 'end', 'narrator', 'license', 'license_url', 'research', 'changes'}, 'audio')
        if lang == 'ru':
            fail('Russian audio redistribution has not been confirmed')
        expected_path = f'/assets/audio/prayer-session/{lang}-psalm118-24.mp3'
        if audio['path'] != expected_path:
            fail(f'{lang}: invalid clip path')
        for key in ('narrator', 'license', 'research', 'changes'):
            text(audio[key], f'{lang}.audio.{key}')
        if audio['license_url'] != {'en': 'https://bereanbible.com/audio/', 'uk': 'http://www.blagovestnik.org/ukraine/ukraine.htm'}[lang]:
            fail(f'{lang}: unexpected rights source')
        voice = 'bsb_souer' if lang == 'en' else 'kozlov_uk'
        if audio['source_file'] != f'audio/{translation}/{voice}/mp3/19/118.mp3':
            fail(f'{lang}: text and recording translations differ')
        expected_credit = {'en': ('Bob Souer', 'CC0 1.0'), 'uk': ('Ігор Козлов', 'Publisher permission: unrestricted redistribution')}[lang]
        if (audio['narrator'], audio['license']) != expected_credit:
            fail(f'{lang}: unconfirmed narrator or license')
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
    for font in FONTS:
        if not (static_root / f'assets/fonts/{font}.ttf').is_file():
            fail(f'missing font {font}')
    for notice in ('spectral-OFL.txt', 'hanken-grotesk-OFL.txt', 'jetbrains-mono-OFL.txt', 'lampada-MIT.txt', 'lucide.txt', 'prayer-audio.txt'):
        if not (static_root / f'assets/licenses/{notice}').is_file():
            fail(f'missing license notice {notice}')
    return data


def load_demo(demo_id: str = 'prayer-session', demos_dir: Path = DEMOS_DIR, static_root: Path = STATIC_ROOT) -> dict:
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', demo_id):
        raise BuildError(f'invalid prayer demo id {demo_id!r}')
    path = demos_dir / f'{demo_id}.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (OSError, ValueError) as error:
        raise BuildError(f'{path}: invalid or missing prayer demo JSON: {error}') from error
    return validate_demo(data, path, static_root)


def render_demo(data: dict, lang: str, strings: object, instance: str = 'prayer-session') -> str:
    if lang not in LANGS or not isinstance(strings, dict) or set(strings) != STRING_KEYS or any(not isinstance(v, str) or not v.strip() for v in strings.values()):
        raise BuildError(f'Prayer demo: missing or invalid translation for {lang}')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', instance):
        raise BuildError('Prayer demo: invalid instance id')
    env = Environment(loader=FileSystemLoader(ROOT / 'templates/lampada'), autoescape=True, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    remaining = data['timer']['remaining']
    return env.get_template('prayer-session-demo.html').render(
        d=data['locales'][lang], t=strings, lang=lang, prefix=f'pd-{instance}-{lang}', week=data['week'],
        timer=f'{remaining // 60:02}:{remaining % 60:02}', ring_offset=440 * (1 - remaining / data['timer']['total']),
    )
