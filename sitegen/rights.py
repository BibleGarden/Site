"""Validate a committed response from Bible-API's rights catalog, offline."""

from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .errors import BuildError

LANGUAGES = ("en", "ru", "uk")


def validate_registry(data: object) -> dict:
    def require(condition, message):
        if not condition:
            raise BuildError(f"rights snapshot: {message}")

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def localized(value):
        return isinstance(value, dict) and set(value) == set(LANGUAGES) and all(text(value[lang]) for lang in LANGUAGES)

    def url(value):
        if not text(value):
            return False
        try:
            parsed = urlsplit(value)
            return parsed.scheme in ("https", "http") and bool(parsed.hostname) and not any(c.isspace() for c in value)
        except ValueError:
            return False

    require(isinstance(data, dict) and data.get("schema_version") == 1, "expected schema_version 1")
    require(isinstance(data.get("items"), dict) and bool(data["items"]), "items must be a non-empty mapping")
    for item_id, item in data["items"].items():
        require(isinstance(item, dict), f"{item_id}: expected an entry")
        kind = item.get("kind")
        require(kind in ("text", "audio"), f"{item_id}: unknown kind")
        alias = item.get("translation_alias")
        require(isinstance(alias, str) and re.fullmatch(r"[a-z][a-z0-9_]*", alias), f"{item_id}: invalid translation alias")
        voice = item.get("voice_alias")
        expected = f"{kind}:{alias}"
        if kind == "audio":
            require(isinstance(voice, str) and re.fullmatch(r"[a-z][a-z0-9_]*", voice), f"{item_id}: invalid voice alias")
            expected += f":{voice}"
        else:
            require(voice is None, f"{item_id}: text cannot have a voice")
        require(item_id == expected, f"{item_id}: id disagrees with aliases")
        for field in ("title", "attribution", "changes"):
            require(localized(item.get(field)), f"{item_id}: missing EN/RU/UK {field}")
        require(text(item.get("rights_holder")), f"{item_id}: missing rights holder")
        require(isinstance(item.get("sources"), list) and bool(item["sources"]) and all(url(source) for source in item["sources"]), f"{item_id}: invalid sources")
        license = item.get("license")
        basis = item.get("public_domain_basis")
        require((license is None) != (basis is None), f"{item_id}: provide a license or public-domain basis")
        if license is not None:
            require(isinstance(license, dict), f"{item_id}: invalid license")
            licenses = {"CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/", "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/"}
            require(license.get("id") in licenses and license.get("url") == licenses[license["id"]] and text(license.get("name")), f"{item_id}: unknown license or incorrect URL")
            if license["id"] == "CC-BY-SA-4.0":
                require(text(item.get("copyright")), f"{item_id}: missing copyright")
        else:
            require(localized(basis), f"{item_id}: missing public-domain basis")
        if item.get("trademark") is not None:
            require(localized(item["trademark"]), f"{item_id}: missing trademark localization")
        try:
            checked = date.fromisoformat(item["checked_on"])
        except (KeyError, TypeError, ValueError) as error:
            raise BuildError(f"rights snapshot: {item_id}: invalid checked_on") from error
        require(checked <= date.today(), f"{item_id}: future checked_on")
    return data


def load_registry(path: Path) -> dict:
    try:
        return validate_registry(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise BuildError(f"{path}: invalid rights snapshot: {error}") from error
