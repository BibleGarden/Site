"""Strict chapter-stream configuration and local verse timecodes."""
from __future__ import annotations

import math
import os
from ipaddress import IPv4Address, ip_address, ip_network
from urllib.parse import urlsplit

from .lectionary_data import TRANSLATIONS, require

VOICES = {'ru': 'prudovsky', 'uk': 'kozlov_uk'}
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


def attach_audio(passages, lang, snapshot, *, errors=None):
    owned = errors is None
    if owned:
        errors = []
    require(set(snapshot) == {'schema_version', 'exported_on', 'source', 'voices', 'timecodes'}
            and type(snapshot['schema_version']) is int and snapshot['schema_version'] == 1
            and snapshot['voices'] == {l: [TRANSLATIONS[l], v] for l, v in VOICES.items()}
            and set(snapshot['timecodes']) == set(VOICES), 'invalid Gospel timecode snapshot')
    for passage in passages.values():
        passage['audio'] = None
        if passage['book'] not in (40, 41, 42, 43):
            continue
        segments = []
        for verse in passage['verses']:
            key = f"{passage['book']}:{verse['chapter']}:{verse['first']}"
            timing = snapshot['timecodes'][lang].get(key)
            if not isinstance(timing, list) or len(timing) != 2 or not valid_timing(*timing):
                errors.append(f'{lang} {passage["label"]}: missing or invalid timecode {key}')
                segments.append(None)
            else:
                segments.append({'chapter': verse['chapter'], 'begin': timing[0], 'end': timing[1]})
        passage['audio'] = {'translation': TRANSLATIONS[lang], 'voice': VOICES[lang],
                            'chapters': list(dict.fromkeys(v['chapter'] for v in passage['verses'])),
                            'segments': segments}
    if owned:
        require(not errors, 'Gospel timecode errors:\n' + '\n'.join(sorted(set(errors))))


def validate_audio(passage, lang, *, errors=None):
    owned = errors is None
    if owned:
        errors = []
    if passage['book'] not in (40, 41, 42, 43):
        require(passage['audio'] is None, 'unexpected audio for non-Gospel passage')
        return
    audio = passage['audio']
    require(isinstance(audio, dict) and set(audio) == {'translation', 'voice', 'chapters', 'segments'}
            and audio['translation'] == TRANSLATIONS[lang] and audio['voice'] == VOICES[lang]
            and audio['chapters'] == list(dict.fromkeys(v['chapter'] for v in passage['verses']))
            and isinstance(audio['segments'], list) and len(audio['segments']) == len(passage['verses']),
            'missing or invalid Gospel audio')
    for verse, segment in zip(passage['verses'], audio['segments']):
        if not (isinstance(segment, dict) and set(segment) == {'chapter', 'begin', 'end'}
                and type(segment['chapter']) is int and segment['chapter'] == verse['chapter']
                and valid_timing(segment['begin'], segment['end'])):
            errors.append(f'{lang} {passage["book"]}:{verse["chapter"]}:{verse["first"]}: invalid timecode')
    if owned:
        require(not errors, 'Gospel timecode errors:\n' + '\n'.join(sorted(set(errors))))
