"""Strict chapter-stream configuration and local verse timecodes."""
from __future__ import annotations

import math
import os
import re
from ipaddress import IPv4Address, ip_address, ip_network
from urllib.parse import urlsplit

from .lectionary_data import require
from .reading_plan import SOURCE_NT

PRIVATE_IPV4 = tuple(ip_network(network) for network in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def preview_http_host(host):
    if host == 'localhost':
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or (isinstance(address, IPv4Address)
                                   and any(address in network for network in PRIVATE_IPV4))


def validate_config(value, *, preview=False):
    require(isinstance(value, dict) and set(value) == {'base_url', 'site_key'},
            'gospel_audio requires exactly base_url and site_key')
    base, key = value['base_url'], value['site_key']
    require(isinstance(base, str) and base == base.strip() and not any(c.isspace() for c in base)
            and '\\' not in base, 'invalid Gospel audio base_url')
    try:
        url = urlsplit(base)
        port = url.port
    except ValueError:
        require(False, 'invalid Gospel audio base_url')
    require(url.scheme in ('https', 'http') and bool(url.hostname) and url.username is None
            and url.password is None and not url.query and not url.fragment and url.path in ('', '/')
            and (port is None or port > 0), 'Gospel audio base_url must be an HTTP(S) origin')
    require(url.scheme == 'https' or (preview and preview_http_host(url.hostname)),
            'Gospel audio requires HTTPS; preview HTTP requires loopback or RFC 1918 IPv4')
    require(isinstance(key, str) and bool(key) and key == key.strip()
            and not any(c.isspace() for c in key), 'missing or invalid Gospel audio site_key')
    return {'base_url': base.rstrip('/'), 'site_key': key}


def preview_config(value):
    require(isinstance(value, dict) and set(value) == {"base_url", "site_key"},
            "gospel_audio requires exactly base_url and site_key")
    result = dict(value)
    for field, variable in (('base_url', 'GOSPEL_AUDIO_BASE_URL'), ('site_key', 'GOSPEL_AUDIO_SITE_KEY')):
        if variable in os.environ:
            result[field] = os.environ[variable]
    return validate_config(result, preview=True)


def valid_timing(begin, end):
    return (all(type(v) in (int, float) and math.isfinite(v) for v in (begin, end))
            and 0 <= begin < end)


# Active local cep_public registry, audited 2026-10-05. Bondarenko includes music.
EDITIONS = {
    'syn': {'language': 'ru', 'name': 'Синодальный', 'voices': {'prudovsky': 'Илья Прудовский', 'bondarenko': 'Александр Бондаренко · с музыкой'}},
    'bti': {'language': 'ru', 'name': 'Кулаковы', 'voices': {'prozorovsky': 'Никита Семёнов-Прозоровский'}},
    'ubh': {'language': 'uk', 'name': 'Хоменко', 'voices': {'kozlov_uk': 'Ігор Козлов'}},
    'npu': {'language': 'uk', 'name': 'НПУ', 'voices': {'npu_uk': 'Бібліка®'}},
    'bsb': {'language': 'en', 'name': 'Berean Standard Bible', 'voices': {'bsb_souer': 'Bob Souer', 'bsb_david': 'David'}},
    'webus': {'language': 'en', 'name': 'World English Bible', 'voices': {'winfred_henson': 'Winfred Henson'}},
    'webbe': {'language': 'en', 'name': 'WEB British Edition', 'voices': {'web_british': 'WEB British Edition'}},
}
API_BOOKS = [next((i + 45 for i, (_, canonical) in enumerate(SOURCE_NT) if canonical == book), book) for book in range(1,67)]
DEFAULTS = {'ru': ['syn', 'prudovsky'], 'uk': ['ubh', 'kozlov_uk'], 'en': ['bsb', 'bsb_souer']}
UNAVAILABLE = {'missing_text', 'numbering'}


def attach_audio(passages, translation, snapshot):
    require(set(snapshot) == {'schema_version', 'exported_on', 'source', 'voices', 'timecodes', 'invalid'}
            and type(snapshot['schema_version']) is int and snapshot['schema_version'] == 2
            and snapshot['voices'] == {v: t for t, e in EDITIONS.items() for v in e['voices']}
            and set(snapshot['timecodes']) == set(snapshot['voices'])
            and set(snapshot['invalid']) == set(snapshot['voices']), 'invalid reading timecode snapshot')
    for voice, rows in snapshot['timecodes'].items():
        require(isinstance(rows, dict) and isinstance(snapshot['invalid'][voice], dict), 'invalid alignment dictionary')
        invalid = snapshot['invalid'][voice]
        require(set(invalid) == {k for k,v in rows.items() if v is None}, 'unexplained unavailable timecode')
        for key, value in rows.items():
            require(isinstance(key,str) and re.fullmatch(r'[1-9][0-9]?:[1-9][0-9]*:[1-9][0-9]*',key)
                    and int(key.split(':')[0]) <= 66, 'invalid timecode coordinate')
            if value is None:
                raw = invalid[key]
                require(isinstance(raw,list) and len(raw)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in raw)
                        and not valid_timing(*raw), 'invalid unavailable timecode evidence')
            else:
                require(isinstance(value,list) and len(value)==2 and valid_timing(*value), 'invalid source timecode')
    for passage in passages.values():
        if passage.get('unavailable'):
            continue
        passage['audio'] = {}
        for voice in EDITIONS[translation]['voices']:
            segments = [snapshot['timecodes'][voice].get(f"{passage['book']}:{v['chapter']}:{v['first']}") for v in passage['verses']]
            # Coverage exclusions verified against the local recordings / app registry.
            excluded = ((voice == 'bondarenko' and passage['book'] in (13, 14, 22, 23))
                        or (voice == 'npu_uk' and passage['book'] not in (19, *range(40, 67)))
                        or (voice == 'kozlov_uk' and any((passage['book'], v['chapter']) in
                            ((17, 11), (17, 12), (27, 13), (27, 14)) for v in passage['verses'])))
            passage['audio'][voice] = None if excluded or any(s is None for s in segments) else segments


def validate_audio(passage, translation):
    audio = passage['audio']
    require(isinstance(audio, dict) and set(audio) == set(EDITIONS[translation]['voices']), 'invalid reading voices')
    for segments in audio.values():
        if segments is None:
            continue  # Explicitly unavailable recording, never a replacement voice.
        require(isinstance(segments, list) and len(segments) == len(passage['verses']), 'invalid alignment length')
        for segment in segments:
            require(isinstance(segment, list) and len(segment) == 2 and valid_timing(*segment), 'invalid reading timecode')
