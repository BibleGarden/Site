"""Strict reading-time article marker, data validation and no-JS table."""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import re
from pathlib import Path

from .errors import BuildError
from .reading_plan import CHAPTER_COUNTS

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / 'content/bible-garden/calculator/reading-time.json'
PLACEHOLDER = '<div data-reading-time-placeholder="reading-time"></div>'
MARKER_RE = re.compile(r'^<!-- calculator: reading-time -->$')
INTENT_RE = re.compile(r'<!--\s*(?:calculator|calulator|calcualtor|calc|calcuator)\b', re.IGNORECASE)
LANGS = {'syn':'ru', 'bti':'ru', 'bsb':'en', 'webus':'en', 'webbe':'en', 'ubh':'uk', 'npu':'uk'}
VOICES = {'prudovsky':'syn', 'bondarenko':'syn', 'prozorovsky':'bti', 'bsb_souer':'bsb', 'bsb_david':'bsb', 'winfred_henson':'webus', 'web_british':'webbe', 'kozlov_uk':'ubh', 'npu_uk':'npu'}
UNITS = ('verse','paragraph','section','chapter')
STRING_KEYS = {
    'title','scope','chapters_day','finish','voice','not_selected','app_features','speed',
    'pause','pause_seconds','none','multi','second_voice','second_speed','unit','approximation',
    'coverage','missing','method','table_caption','result','minutes_day','date',
    'deadline_hint','invalid','language_en','language_ru','language_uk',
    'scope_bible','scope_ot','scope_nt','table_bible','table_ot','table_nt',
    'unit_verse','unit_paragraph','unit_section','unit_chapter',
    'chapter_units','year_units','month_units','minute_units',
}
PLURAL_KEYS = {'chapter_units','year_units','month_units','minute_units'}


def annotate_calculator_marker(body: str, source: Path, site: str, body_start_line: int = 1) -> tuple[str, bool]:
    from .content import _fenced_flags
    lines = body.splitlines()
    fenced = _fenced_flags(lines)
    found = False
    for index, line in enumerate(lines):
        if fenced[index] or not INTENT_RE.search(line):
            continue
        if not MARKER_RE.fullmatch(line):
            raise BuildError(f'{source}:{body_start_line+index}: expected <!-- calculator: reading-time -->')
        if site != 'bible-garden':
            raise BuildError(f'{source}:{body_start_line+index}: calculator is only supported on bible-garden')
        if found:
            raise BuildError(f'{source}:{body_start_line+index}: duplicate calculator marker')
        lines[index], found = PLACEHOLDER, True
    return '\n'.join(lines) + ('\n' if body.endswith('\n') else ''), found


def _keys(value: object, expected: set, context: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise BuildError(f'reading time: {context}: expected keys {sorted(expected)}')


def _number(value: object, context: str, *, integer: bool = False, positive: bool = False) -> None:
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError):
        finite = False
    if type(value) not in ((int,) if integer else (int,float)) or not finite or value < 0 or (positive and value==0):
        raise BuildError(f'reading time: {context}: invalid number {value!r}')


def _names(value: object, context: str) -> None:
    _keys(value, {'en','ru','uk'}, context)
    if any(not isinstance(x,str) or not x.strip() for x in value.values()):
        raise BuildError(f'reading time: {context}: empty localized name')


def validate_data(data: dict) -> None:
    _keys(data, {'schema_version','measured_on','method','books','voices'}, 'data')
    if type(data['schema_version']) is not int or data['schema_version']!=2 or data['method']!='mp3-decoded':
        raise BuildError('reading time: unknown schema or method')
    try:
        if not isinstance(data['measured_on'],str) or dt.date.fromisoformat(data['measured_on']).isoformat()!=data['measured_on']:
            raise ValueError('date must be ISO YYYY-MM-DD')
    except (TypeError,ValueError) as error:
        raise BuildError('reading time: invalid measured_on date') from error
    if not isinstance(data['books'],list) or len(data['books'])!=66:
        raise BuildError('reading time: expected 66 books')
    for number, book in enumerate(data['books'],1):
        _keys(book, {'id','names','chapters'},f'book {number}')
        if type(book['id']) is not int or book['id']!=number:
            raise BuildError('reading time: books must be in canonical order')
        if type(book['chapters']) is not int or book['chapters'] != CHAPTER_COUNTS[number-1]:
            raise BuildError(f'reading time: book {number}: invalid canonical chapter count')
        _names(book['names'], f'book {number}')
    _keys(data['voices'], set(VOICES), 'voices')
    for key, record in data['voices'].items():
        _keys(record, {'lang','names','books'},key)
        translation = VOICES[key]
        if record['lang'] != LANGS[translation]:
            raise BuildError(f'reading time: invalid language for {key}')
        _names(record['names'],key)
        allowed = set(range(1,67))
        if key=='bondarenko':
            allowed -= {13,14,22,23}
        if translation=='npu':
            allowed = {19,*range(40,67)}
        _keys(record['books'], {str(b) for b in allowed},f'{key} coverage')
        for b, book in record['books'].items():
            context = f'{key} book {b}'
            _keys(book, {'chapters','units','seconds'},context)
            expected_chapters = 3 if translation=='ubh' and b=='39' else CHAPTER_COUNTS[int(b)-1]
            if type(book['chapters']) is not int or book['chapters'] != expected_chapters:
                raise BuildError(f'reading time: {context}: chapter coverage mismatch')
            _number(book['seconds'], context,positive=True)
            _keys(book['units'],set(UNITS),context+' units')
            for unit, values in book['units'].items():
                _keys(values, {'count','seconds'},context+' '+unit)
                _number(values['count'],context,integer=True,positive=True)
                _number(values['seconds'],context)
            for unit, values in book['units'].items():
                if values['count'] < expected_chapters or values['count'] > book['units']['verse']['count'] or (unit=='chapter' and values['count']!=expected_chapters):
                    raise BuildError(f'reading time: {context}: invalid unit count')
                if values['seconds'] > book['seconds']+.001 or values['seconds'] > book['units']['chapter']['seconds']+.001:
                    raise BuildError(f'reading time: {context}: span exceeds audio')


def _unique_keys(pairs: list) -> dict:
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError(f'duplicate JSON key {key}')
        value[key]=item
    return value


def load_data(path: Path = DATA_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=_unique_keys)
    except (OSError,ValueError) as error:
        raise BuildError(f'{path}: invalid or missing reading-time data: {error}') from error
    validate_data(data)
    return data


def plural(number: int, lang: str, forms: dict) -> str:
    if lang == 'en':
        category = 'one' if number==1 else 'other'
    elif number%10==1 and number%100!=11:
        category = 'one'
    elif 2<=number%10<=4 and not 12<=number%100<=14:
        category = 'few'
    else:
        category = 'many'
    return forms[category]


def duration_label(days: int, lang: str, strings: dict) -> str:
    """Reference durations rounded to months; no arbitrary start date is implied."""
    months = max(1, math.floor(days*12/365+.5))
    years, months = divmod(months,12)
    parts = []
    if years:
        parts.append(f'{years} {plural(years,lang,strings["year_units"])}')
    if months:
        parts.append(f'{months} {plural(months,lang,strings["month_units"])}')
    return ' '.join(parts)


def render_calculator(data: dict, lang: str, strings: dict) -> str:
    validate_data(data)
    if lang not in {'en','ru','uk'}:
        raise BuildError(f'reading time: unknown language {lang}')
    _keys(strings, STRING_KEYS,'i18n')
    for key,value in strings.items():
        if key in PLURAL_KEYS:
            _keys(value,{'one','few','many','other'},f'i18n {key}')
            values = value.values()
        else:
            values = [value]
        if any(not isinstance(v,str) or not v.strip() for v in values):
            raise BuildError(f'reading time: invalid i18n value for {key}')
    import string
    for key,expected in [('result',{'count','chapters','date'}),('minutes_day',{'minutes','unit'}),('date',{'day','month','year'}),('coverage',{'recorded','total'})]:
        try:
            parts = list(string.Formatter().parse(strings[key]))
            if any(spec or conversion for _literal,field,spec,conversion in parts):
                raise ValueError('unsupported format syntax')
            fields = {field for _literal,field,spec,conversion in parts if field is not None}
            if fields!=expected:
                raise ValueError('unexpected placeholders')
            strings[key].format(**{field:'test' for field in expected})
        except (ValueError,KeyError,IndexError) as error:
            raise BuildError(f'reading time: invalid i18n template {key}') from error
    t = {key:html.escape(value,quote=True) for key,value in strings.items() if key not in PLURAL_KEYS}
    def select(name: str, label: str, options: list[tuple[str,str]], default: str) -> str:
        option_fragments = []
        for key,value in options:
            selected = ' selected' if key==default else ''
            option_fragments.append(f'<option value="{html.escape(key)}"{selected}>{value}</option>')
        return ''.join([
            f'<label for="rt-{name}">{label}',
            f'<select id="rt-{name}" name="{name}">',
            *option_fragments,
            '</select></label>',
        ])

    def recording(name: str, optional: bool=False) -> str:
        groups = [f'<option value="" selected>{t["not_selected"]}</option>'] if optional else []
        for language in ('ru','en','uk'):
            options = []
            for key in VOICES:
                record = data['voices'][key]
                if record['lang']==language:
                    selected = ' selected' if not optional and key=='bsb_souer' else ''
                    label = html.escape(record['names'][lang])
                    options.append(f'<option value="{key}"{selected}>{label}</option>')
            groups.extend([
                f'<optgroup label="{t["language_"+language]}">',
                *options,
                '</optgroup>',
            ])
        label = t['voice' if optional else 'second_voice']
        return ''.join([
            f'<label for="rt-{name}">{label}',
            f'<select id="rt-{name}" name="{name}">',
            *groups,
            '</select></label>',
        ])

    def number(name: str, label: str, value: float, low: float, step: float, high: float | None=None) -> str:
        maximum = f' max="{high}"' if high is not None else ''
        return ''.join([
            f'<label for="rt-{name}">{label}',
            f'<input id="rt-{name}" name="{name}" type="number"',
            f' value="{value}" min="{low}" step="{step}"{maximum} required>',
            '</label>',
        ])

    units = [(unit,t['unit_'+unit]) for unit in UNITS]
    primary_controls = [
        select('scope',t['scope'],[(scope,t['scope_'+scope]) for scope in ('bible','ot','nt')],'bible'),
        number('chapters_day',t['chapters_day'],3,1,1),
        f'<label for="rt-finish">{t["finish"]}',
        '<input id="rt-finish" name="finish" type="date" required aria-describedby="rt-deadline-hint">',
        '</label>',
        recording('voice',True),
        f'<p id="rt-deadline-hint" class="reading-time-note">{t["deadline_hint"]}</p>',
    ]
    multi_controls = [
        '<div data-multi hidden>',
        recording('voice_b'),
        number('speed_b',t['second_speed'],1,.5,.1,2.5),
        select('unit',t['unit'],units,'verse'),
        f'<p class="reading-time-note">{t["approximation"]}</p>',
        '</div>',
    ]
    audio_controls = [
        '<details class="reading-time-audio" hidden>',
        f'<summary>{t["app_features"]}</summary>',
        '<div class="reading-time-settings">',
        number('speed',t['speed'],1,.6,.2,2),
        '<div data-normal>',
        select('pause_unit',t['pause'],[('none',t['none']),*units[:3]],'none'),
        '</div>',
        '<div data-pause hidden>',
        number('pause',t['pause_seconds'],0,0,.1,60),
        '</div>',
        f'<label class="reading-time-check"><input type="checkbox" name="multi">{t["multi"]}</label>',
        *multi_controls,
        '</div></details>',
    ]
    scope_chapters = {
        scope:sum(book['chapters'] for book in data['books']
                  if scope=='bible' or (book['id']<=39)==(scope=='ot'))
        for scope in ('bible','ot','nt')
    }
    reference_table = [
        '<div class="reading-time-table"><table>',
        f'<caption>{t["table_caption"]}</caption>',
        f'<thead><tr><th scope="col">{t["chapters_day"]}</th>',
    ]
    for scope in scope_chapters:
        reference_table.append(
            f'<th scope="col"><abbr title="{t["scope_"+scope]}">{t["table_"+scope]}</abbr></th>'
        )
    reference_table.append('</tr></thead><tbody>')
    for per_day in (1,2,3,4,5,10):
        reference_table.append(f'<tr><th scope="row">{per_day}</th>')
        for total in scope_chapters.values():
            label = html.escape(duration_label(math.ceil(total/per_day),lang,strings))
            reference_table.append(f'<td>{label}</td>')
        reference_table.append('</tr>')
    reference_table.append('</tbody></table></div>')
    payload = json.dumps(dict(data=data,strings=strings,lang=lang),ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    calculator_card = [
        '<section class="reading-time" aria-labelledby="reading-time-title">',
        f'<h3 id="reading-time-title">{t["title"]}</h3>',
        '<form class="reading-time-form" hidden>',
        *primary_controls,
        *audio_controls,
        '<div class="reading-time-result" aria-live="polite" aria-atomic="true" hidden></div>',
        '</form>',
        f'<script type="application/json" data-reading-time-data>{payload}</script>',
        '</section>',
    ]
    method_caption = [
        f'<p class="reading-time-method">{t["method"]} ',
        f'<time datetime="{data["measured_on"]}">{data["measured_on"]}</time>.</p>',
    ]
    return ''.join([*reference_table,*calculator_card,*method_caption])
