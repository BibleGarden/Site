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
DEFAULTS = {'en':('bsb_souer','bsb',238), 'ru':('prudovsky','syn',190), 'uk':('kozlov_uk','ubh',190)}
UNITS = ('verse','paragraph','section','chapter')
STRING_KEYS = {
    'title','mode','listen','silent','voice','translation','scope','book','speed','pause','pause_seconds',
    'none','multi','second_voice','first_step','second_step','unit','start','plan','daily','deadline',
    'minutes','finish','total','speech','pauses','days','minutes_day','missing','empty','method','approximation',
    'silent_method','wpm','table_caption','invalid','language_en','language_ru','language_uk',
    'scope_bible','scope_ot','scope_nt','scope_gospels','scope_psalms','scope_book','table_bible','table_ot','table_nt',
    'unit_verse','unit_paragraph','unit_section','unit_chapter',
}


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
    _keys(data, {'schema_version','measured_on','method','books','voices','translations'}, 'data')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['method']!='mp3-decoded':
        raise BuildError('reading time: unknown schema or method')
    try:
        if not isinstance(data['measured_on'],str) or dt.date.fromisoformat(data['measured_on']).isoformat()!=data['measured_on']:
            raise ValueError('date must be ISO YYYY-MM-DD')
    except (TypeError,ValueError) as error:
        raise BuildError('reading time: invalid measured_on date') from error
    if not isinstance(data['books'],list) or len(data['books'])!=66:
        raise BuildError('reading time: expected 66 books')
    for number, book in enumerate(data['books'],1):
        _keys(book, {'id','names'},f'book {number}')
        if type(book['id']) is not int or book['id']!=number:
            raise BuildError('reading time: books must be in canonical order')
        _names(book['names'], f'book {number}')
    _keys(data['voices'], set(VOICES), 'voices')
    _keys(data['translations'], set(LANGS), 'translations')
    for kind, registry in [('voices',VOICES),('translations',LANGS)]:
        for key, record in data[kind].items():
            _keys(record, {'translation' if kind=='voices' else 'lang','names','books'},key)
            if record['translation' if kind=='voices' else 'lang'] != registry[key]:
                raise BuildError(f'reading time: invalid registry entry {key}')
            _names(record['names'],key)
            translation = VOICES[key] if kind=='voices' else key
            allowed = set(range(1,67))
            if key=='bondarenko':
                allowed -= {13,14,22,23}
            if translation=='npu':
                allowed = {19,*range(40,67)}
            _keys(record['books'], {str(b) for b in allowed},f'{key} coverage')
            for b, book in record['books'].items():
                context = f'{key} book {b}'
                _keys(book, {'chapters','units','seconds' if kind=='voices' else 'words'},context)
                expected_chapters = 3 if translation=='ubh' and b=='39' else CHAPTER_COUNTS[int(b)-1]
                if type(book['chapters']) is not int or book['chapters'] != expected_chapters:
                    raise BuildError(f'reading time: {context}: chapter coverage mismatch')
                _number(book['seconds' if kind=='voices' else 'words'], context, integer=kind!='voices',positive=True)
                _keys(book['units'],set(UNITS),context+' units')
                for unit, values in book['units'].items():
                    _keys(values, {'count','seconds'} if kind=='voices' else {'count'},context+' '+unit)
                    _number(values['count'],context,integer=True,positive=True)
                    if kind=='voices':
                        _number(values['seconds'],context)
                for unit, values in book['units'].items():
                    if values['count'] < expected_chapters or values['count'] > book['units']['verse']['count'] or (unit=='chapter' and values['count']!=expected_chapters):
                        raise BuildError(f'reading time: {context}: invalid unit count')
                    if kind=='voices':
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


def h_mm(seconds: float) -> str:
    minutes = math.ceil(seconds/60)
    return f'{minutes//60}:{minutes%60:02d}'


def render_calculator(data: dict, lang: str, strings: dict) -> str:
    validate_data(data)
    if lang not in DEFAULTS:
        raise BuildError(f'reading time: unknown language {lang}')
    _keys(strings, STRING_KEYS,'i18n')
    if any(not isinstance(s,str) or not s.strip() for s in strings.values()):
        raise BuildError('reading time: invalid i18n value')
    t = {k:html.escape(v,quote=True) for k,v in strings.items()}
    voice, translation, wpm = DEFAULTS[lang]
    def select(name: str, label: str, options: list[tuple[str,str]], default: str, attrs: str='') -> str:
        opts = ''.join(f'<option value="{html.escape(key)}"'+(' selected' if key==default else '')+f'>{value}</option>' for key,value in options)
        return f'<label for="rt-{name}">{label}<select id="rt-{name}" name="{name}" {attrs}>{opts}</select></label>'
    def recording(name: str, kind: str, default: str) -> str:
        groups=[]
        for language in ('ru','en','uk'):
            opts=[]
            for key,record in data[kind].items():
                rec_lang = LANGS[record['translation']] if kind=='voices' else record['lang']
                if rec_lang==language:
                    opts.append(f'<option value="{key}"'+(' selected' if key==default else '')+f'>{html.escape(record["names"][lang])}</option>')
            groups.append(f'<optgroup label="{t["language_"+language]}">'+''.join(opts)+'</optgroup>')
        return f'<label for="rt-{name}">{t["voice" if kind=="voices" else "translation"]}<select id="rt-{name}" name="{name}">'+''.join(groups)+'</select></label>'
    def number(name: str, label: str, value: float, low: float, high: float, step: float) -> str:
        return f'<label for="rt-{name}">{label}<input id="rt-{name}" name="{name}" type="number" value="{value}" min="{low}" max="{high}" step="{step}" required></label>'
    units=[(u,t['unit_'+u]) for u in UNITS]
    form = [select('mode',t['mode'],[('listen',t['listen']),('silent',t['silent'])],'listen'),
            '<div data-listen>'+recording('voice','voices',voice)+'</div>',
            '<div data-silent hidden>'+recording('translation','translations',translation)+number('wpm',t['wpm'],wpm,1,2000,1)+f'<p class="reading-time-note">{t["silent_method"]}</p></div>',
            select('scope',t['scope'],[(s,t['scope_'+s]) for s in ('bible','ot','nt','gospels','psalms','book')],'bible'),
            '<div data-book hidden>'+select('book',t['book'],[(str(b['id']),html.escape(b['names'][lang])) for b in data['books']],'1')+'</div>',
            '<div data-normal>'+number('speed',t['speed'],1,.6,2,.2)+select('pause_unit',t['pause'],[('none',t['none']),*units[:3]],'none')+f'<div data-pause hidden>{number("pause",t["pause_seconds"],0,0,60,.1)}</div></div>',
            '<div data-listen><details class="reading-time-multi"><summary>'+t['multi']+'</summary><label class="reading-time-check"><input type="checkbox" name="multi">'+t['second_voice']+'</label><div data-multi hidden>'+select('unit',t['unit'],units,'verse')+
            f'<fieldset><legend>{t["first_step"]}</legend>'+number('speed_a',t['speed'],1,.5,2.5,.1)+number('pause_a',t['pause_seconds'],2,0,60,.1)+'</fieldset>'+f'<fieldset><legend>{t["second_step"]}</legend>'+recording('voice_b','voices','bsb_souer' if voice!='bsb_souer' else 'prudovsky')+number('speed_b',t['speed'],1,.5,2.5,.1)+number('pause_b',t['pause_seconds'],2,0,60,.1)+f'</fieldset><p class="reading-time-note">{t["approximation"]}</p></div></details></div>',
            f'<fieldset><legend>{t["plan"]}</legend><label for="rt-start">{t["start"]}<input id="rt-start" name="start" type="date" required></label>'+select('plan',t['plan'],[('daily',t['daily']),('deadline',t['deadline'])],'daily')+f'<div data-daily>{number("minutes",t["minutes"],15,.1,1440,.1)}</div><div data-deadline hidden><label for="rt-finish">{t["finish"]}<input id="rt-finish" name="finish" type="date" required></label></div></fieldset>']
    table = [f'<div class="reading-time-table"><table><caption>{t["table_caption"]}</caption><thead><tr><th scope="col">{t["voice"]} / {t["translation"]}</th>'+''.join(f'<th scope="col"><abbr title="{t["scope_"+s]}">{t["table_"+s]}</abbr></th>' for s in ('bible','ot','nt'))+'</tr></thead><tbody>']
    for kind in ('voices','translations'):
        for key,record in data[kind].items():
            record_lang = LANGS[record['translation']] if kind=='voices' else record['lang']
            if record_lang!=lang:
                continue
            missing = [b['names'][lang] for b in data['books'] if str(b['id']) not in record['books']]
            label = html.escape(record['names'][lang]) + (f' ({t["silent"]}, {wpm} {t["wpm"]})' if kind=='translations' else '')
            if missing:
                label += f'<small>{t["missing"]}: '+html.escape(', '.join(missing))+'</small>'
            cells=[]
            for scope in ('bible','ot','nt'):
                books=[v for b,v in record['books'].items() if scope=='bible' or (int(b)<=39)==(scope=='ot')]
                seconds=sum(v['seconds'] if kind=='voices' else v['words']/wpm*60 for v in books)
                cells.append(f'<td>{h_mm(seconds) if books else t["empty"]}</td>')
            table.append(f'<tr><th scope="row">{label}</th>'+''.join(cells)+'</tr>')
    table.append('</tbody></table></div>')
    payload=json.dumps(dict(data=data,strings=strings,lang=lang),ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    return '<section class="reading-time" aria-labelledby="reading-time-title">'+f'<h3 id="reading-time-title">{t["title"]}</h3><form class="reading-time-form" hidden>'+''.join(form)+'</form><div class="reading-time-result" aria-live="polite" aria-atomic="true" hidden></div>'+''.join(table)+f'<p class="reading-time-note">{t["method"]} <time datetime="{data["measured_on"]}">{data["measured_on"]}</time>.</p><script type="application/json" data-reading-time-data>{payload}</script></section>'
