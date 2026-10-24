"""Check the rendering contract of an already validated API rights snapshot."""

import json
from pathlib import Path

from .errors import BuildError

LANGUAGES = ("en", "ru", "uk")
TEMPLATE_FIELDS = {"kind", "title", "rights_holder", "credit", "copyright", "license",
                   "public_domain_basis", "permission", "attribution", "changes", "trademark", "sources", "checked_on"}


def validate_registry(data: object) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise BuildError("rights snapshot: expected schema_version 1")
    if not isinstance(data.get("items"), dict):
        raise BuildError("rights snapshot: missing items mapping")
    for item_id, item in data["items"].items():
        # Schema v1 snapshots predating permission omit this newly added nullable field.
        if not isinstance(item, dict) or not TEMPLATE_FIELDS - {"permission"} <= item.keys():
            raise BuildError(f"rights snapshot: {item_id}: missing template fields")
        bases = [field for field in ("license", "public_domain_basis", "permission") if item.get(field) is not None]
        if len(bases) != 1:
            raise BuildError(f"rights snapshot: {item_id}: expected exactly one license, public_domain_basis or permission")
        if item.get("permission") is not None:
            if not isinstance(item["rights_holder"], str) or not item["rights_holder"].strip():
                raise BuildError(f"rights snapshot: {item_id}: permission requires rights_holder")
            permission = item["permission"]
            if not isinstance(permission, dict) or any(
                not isinstance(permission.get(lang), str) or not permission[lang].strip() for lang in LANGUAGES
            ):
                raise BuildError(f"rights snapshot: {item_id}: missing EN/RU/UK permission")
        localized = ["title", "attribution", "changes"]
        localized += [field for field in ("credit", "trademark") if item[field] is not None]
        if item["public_domain_basis"] is not None:
            localized.append("public_domain_basis")
        if item["license"] is not None and (
            not isinstance(item["license"], dict) or not {"name", "url"} <= item["license"].keys()
        ):
            raise BuildError(f"rights snapshot: {item_id}: missing license display fields")
        for field in localized:
            if not isinstance(item[field], dict) or not set(LANGUAGES) <= item[field].keys():
                raise BuildError(f"rights snapshot: {item_id}: missing EN/RU/UK {field}")
        if not isinstance(item["sources"], list):
            raise BuildError(f"rights snapshot: {item_id}: missing sources list")
    return data


def load_registry(path: Path) -> dict:
    try:
        return validate_registry(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise BuildError(f"{path}: invalid rights snapshot: {error}") from error
