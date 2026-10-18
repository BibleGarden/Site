"""Offline article evidence schema and public, metadata-only footnotes."""

import html
import re

import markdown
from urllib.parse import urlsplit

from .errors import BuildError

FIELDS = {"id", "chunk_id", "book_id", "char_start", "char_end", "text_sha256",
          "kind", "text", "original", "translation", "author", "title", "chapter", "translator", "source_url"}


def citation_chapter(label):
    """Map the API's explicit empty locator to article null; never invent one."""
    if not isinstance(label, str) or (label and not label.strip()):
        raise ValueError("citation_label must be a string, empty only when no locator is proven")
    return label if label else None


def citations(value, body, source):
    if not isinstance(value, list):
        raise BuildError(f"{source}: corpus_sources must be a list")
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise BuildError(f"{source}: corpus source requires exactly {sorted(FIELDS)}")
        for key in FIELDS - {"book_id", "char_start", "char_end", "translator", "chapter", "original", "translation"}:
            if not isinstance(item[key], str) or not item[key].strip():
                raise BuildError(f"{source}: source {key} must be non-empty text")
        for key in ("chapter", "translator"):
            if item[key] is not None and (not isinstance(item[key], str) or not item[key].strip()):
                raise BuildError(f"{source}: {key} must be non-empty text or null")
        for key in ("book_id", "char_start", "char_end"):
            if type(item[key]) is not int:
                raise BuildError(f"{source}: {key} must be an integer")
        if not (item["book_id"] > 0 and 0 <= item["char_start"] < item["char_end"]):
            raise BuildError(f"{source}: invalid book ID or character range")
        ident = item["id"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", ident) or ident in seen:
            raise BuildError(f"{source}: invalid or duplicate corpus source id {ident!r}")
        seen.add(ident)
        if item["kind"] not in {"quote", "retelling"}:
            raise BuildError(f"{source}: kind must be quote or retelling")
        if item["translation"] not in (None, "ours", "published"):
            raise BuildError(f"{source}: translation must be ours, published or null")
        if item["kind"] == "quote":
            if not isinstance(item["original"], str) or not item["original"].strip():
                raise BuildError(f"{source}: quote original must be a non-empty verbatim span")
            if item["translation"] == "published" and not item["translator"]:
                raise BuildError(f"{source}: published translation requires the source edition translator")
        elif item["original"] is not None or item["translation"] is not None:
            raise BuildError(f"{source}: retelling original and translation must be null")
        if not re.fullmatch(r"[a-f0-9]{64}", item["text_sha256"]):
            raise BuildError(f"{source}: invalid text_sha256")
        url = urlsplit(item["source_url"])
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise BuildError(f"{source}: source_url must be an absolute HTTP(S) URL")
        marker = f"[^corpus-{ident}]"
        if body.count(marker) != 1 or not re.search(re.escape(item["text"]) + r"[\s»”’\"'.,;:!?…\)\]]*" + re.escape(marker), body):
            raise BuildError(f"{source}: supported text must occur immediately before {marker}, exactly once")
    markers = set(re.findall(r"\[\^corpus-([^\]]+)\]", body))
    if markers != seen:
        raise BuildError(f"{source}: corpus markers and corpus_sources differ")
    if value:
        rendered = markdown.markdown(annotate(body, value, "en"), extensions=["extra"])
        for item in value:
            if rendered.count(f'id="fnref:corpus-{item["id"]}"') != 1:
                raise BuildError(f"{source}: corpus marker must render as a prose footnote, outside code/comments")
    return value


def annotate(body, sources, lang):
    labels = {"en": "translated by", "ru": "перевод", "uk": "переклад"}
    ours = {"en": "our translation", "ru": "наш перевод", "uk": "наш переклад"}
    for item in sources:
        label = f'{item["author"]}. {item["title"]}'
        # chapter already contains the complete API citation_label.
        if item["chapter"]:
            label += f'. {item["chapter"]}'
        if item["translator"]:
            label += f', {labels[lang]} {item["translator"]}'
        if item["translation"] == "ours":
            label += f', {ours[lang]}'
        label += f' ({urlsplit(item["source_url"]).hostname})'
        # Raw HTML is escaped here; corpus IDs, offsets and source fragments stay private.
        link = f'<a href="{html.escape(item["source_url"], quote=True)}">{html.escape(label)}</a>'
        body += f'\n\n[^corpus-{item["id"]}]: {link}\n'
    return body
