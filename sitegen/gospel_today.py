"""Strict article marker and an honest no-JavaScript daily-reading shell."""
from __future__ import annotations

import html
import json
import re

from .errors import BuildError
from .lectionary_data import CALENDARS, load_bundle, require

PLACEHOLDER = '<div data-gospel-today-placeholder="gospel-today"></div>'
MARKER = '<!-- gospel-today -->'
INTENT = re.compile(r'<!--\s*(?:gospel[-_ ]?today|gospel-tody)\b', re.I)
STRING_KEYS = {'title', 'calendar', 'no_js', 'loading', 'error', 'out_of_range',
               'uncertain', 'ordinary_may_be_omitted', 'saints', 'gospel', 'apostle', 'ot',
               'no_liturgy', 'royal_hours', 'hour', 'ordinary', 'feast', 'special', 'triodion',
               'pentecostarion', 'no_liturgy_gospel', 'no_liturgy_vespers_gospel', 'presanctified', 'app', 'app_hint', 'radio_gospel', 'radio_apostle', 'calendar_link', 'audio_play', 'audio_pause', 'audio_again', 'audio_error', 'audio_progress', 'audio_verse', 'language', 'narrator', 'edition', 'reading_play', 'missing_text', 'missing_audio', 'numbering', 'nothing_playable'}


def annotate_marker(body, source, site, lang, body_start_line=1):
    from .content import _fenced_flags
    lines = body.splitlines()
    fenced = _fenced_flags(lines)
    found = False
    for index, line in enumerate(lines):
        if fenced[index] or not INTENT.search(line):
            continue
        if line != MARKER:
            raise BuildError(f'{source}:{body_start_line + index}: expected {MARKER}')
        require(site == 'bible-garden' and lang in CALENDARS, 'gospel-today only supports bible-garden ru/uk')
        require(not found, 'duplicate gospel-today marker')
        lines[index], found = PLACEHOLDER, True
    return '\n'.join(lines) + ('\n' if body.endswith('\n') else ''), found


def validate_strings(strings):
    require(isinstance(strings, dict) and set(strings) == STRING_KEYS, 'missing or unknown gospel-today translations')
    require(all(isinstance(v, str) and bool(v.strip()) for v in strings.values()), 'empty gospel-today translation')
    require('{verse}' in strings['audio_verse'], 'invalid audio verse label')
    require('{reading}' in strings['reading_play'], 'invalid reading play label')
    require('{chapter}' in strings['app_hint'] and '{verse}' in strings['app_hint'] and '{book}' in strings['app_hint'], 'invalid app hint')


def render_component(lang, strings, app_store_url, audio_config=None, *, preview=False):
    require(lang in CALENDARS, 'unsupported gospel-today language')
    validate_strings(strings)
    manifest, _ = load_bundle()
    require(isinstance(app_store_url, str) and app_store_url.startswith('https://apps.apple.com/'), 'missing App Store URL')
    escape = html.escape
    from .gospel_audio import validate_config
    audio_config = validate_config(audio_config, preview=preview)
    from .gospel_audio import EDITIONS, DEFAULTS, API_BOOKS
    config = {'editions': EDITIONS, 'defaults': DEFAULTS, 'audio': {**audio_config, 'books': API_BOOKS}, 'lang': lang, 'start_year': manifest['start_year'], 'end_year': manifest['end_year'], 'strings': strings}
    config_json = json.dumps(config, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    if lang == 'ru':
        links = f'<a href="https://radiovera.ru/gospel.html">{escape(strings["radio_gospel"])}</a> · <a href="https://radiovera.ru/apostol.html">{escape(strings["radio_apostle"])}</a>'
    else:
        links = f'<a href="https://www.pomisna.info/uk/tserkva/kalendar/">{escape(strings["calendar_link"])}</a>'
    return f'''<section class="gospel-today" aria-labelledby="gospel-today-title" data-gospel-today>
<header class="gospel-today-header"><h2 id="gospel-today-title">{escape(strings['title'])}</h2>
<time data-gospel-date></time><p class="gospel-calendar">{escape(strings['calendar'])}</p></header>
<div data-gospel-selectors class="gospel-selectors" hidden></div>
<div class="gospel-today-window">
<p data-gospel-status role="status" aria-live="polite">{escape(strings['no_js'])}</p>
<div data-gospel-readings></div>
</div>
<script type="application/json" data-gospel-config>{config_json}</script>
</section>
<div class="gospel-today-links" data-gospel-links>
<p>{links} · <a href="{escape(app_store_url)}" data-umami-event="app-store-click" target="_blank" rel="noopener">{escape(strings['app'])}</a></p>
<p data-gospel-app-hint></p>
<p>{escape(strings['saints'])}</p>
</div>'''
