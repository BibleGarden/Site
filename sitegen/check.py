"""Validation of the generated HTML: JSON-LD contents and hreflang targets."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .build import CONTENT_DIR, REPO_ROOT
from .content import load_site
from .errors import BuildError

JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)">')
HREFLANG_RE = re.compile(r'<link rel="alternate" hreflang="[^"]+" href="([^"]+)">')
NOINDEX_RE = re.compile(r'<meta name="robots" content="noindex">')
ANCHOR_HREF_RE = re.compile(r'<a\s[^>]*?href="([^"]+)"')
SKIPPED_DIRS = {".git", "content", "templates", "sitegen", ".venv"}


def html_files() -> list[Path]:
    return sorted(
        path for path in REPO_ROOT.rglob("*.html") if not SKIPPED_DIRS & set(path.relative_to(REPO_ROOT).parts)
    )


def run_checks() -> tuple[int, int]:
    """Return (JSON-LD blocks, hreflang links) after validating every generated HTML file."""
    pages = {path: path.read_text(encoding="utf-8") for path in html_files()}
    blocks = sum(check_json_ld(path, html) for path, html in pages.items())
    links = check_hreflang(pages)
    check_internal_links(pages)
    return blocks, links


def check_json_ld(path: Path, html: str) -> int:
    count = 0
    for match in JSON_LD_RE.finditer(html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as error:
            raise BuildError(f"{path}: invalid JSON-LD: {error}") from error
        if not isinstance(data, dict) or data.get("@context") != "https://schema.org":
            raise BuildError(f"{path}: JSON-LD block must be an object with @context https://schema.org")
        kind = data.get("@type")
        if kind == "Article":
            _require(path, data, "headline", "image", "datePublished", "dateModified", "description", "inLanguage")
            _require(path, data["author"], "name")
            _require(path, data["publisher"], "name", "logo")
        elif kind == "BreadcrumbList":
            _require_list(path, data, "itemListElement")
            for item in data["itemListElement"]:
                _require(path, item, "position", "name", "item")
        elif kind == "FAQPage":
            _require_list(path, data, "mainEntity")
            for question in data["mainEntity"]:
                _require(path, question, "name")
                _require(path, question["acceptedAnswer"], "text")
        else:
            raise BuildError(f"{path}: unexpected JSON-LD @type {kind!r}")
        count += 1
    return count


def _require(path: Path, data: object, *keys: str) -> None:
    if not isinstance(data, dict):
        raise BuildError(f"{path}: JSON-LD expected an object with {', '.join(keys)}")
    for key in keys:
        if not data.get(key):
            raise BuildError(f"{path}: JSON-LD field {key!r} is missing or empty")


def _require_list(path: Path, data: dict, key: str) -> None:
    if not isinstance(data.get(key), list) or not data[key]:
        raise BuildError(f"{path}: JSON-LD field {key!r} must be a non-empty list")


def check_hreflang(pages: dict[Path, str]) -> int:
    """Every hreflang link must point at an indexable page; noindex pages are never alternates."""
    noindex_urls = {
        CANONICAL_RE.search(html).group(1)
        for html in pages.values()
        if NOINDEX_RE.search(html) and CANONICAL_RE.search(html)
    }
    links = 0
    for path, html in pages.items():
        for href in HREFLANG_RE.findall(html):
            if href in noindex_urls:
                raise BuildError(f"{path}: hreflang points at a noindex page {href}")
            links += 1
    return links


def check_internal_links(pages: dict[Path, str]) -> None:
    """Navigation inside a site must be root-relative so previews stay on the preview host."""
    sites = [load_site(directory, REPO_ROOT) for directory in sorted(CONTENT_DIR.iterdir()) if directory.is_dir()]
    for path, html in pages.items():
        # The most specific output directory owns the page (lampada/ is nested in the repository root).
        owner = max((site for site in sites if path.is_relative_to(site.output_dir)), key=lambda site: len(site.output_dir.parts))
        for href in ANCHOR_HREF_RE.findall(html):
            if href == owner.base_url or href.startswith(owner.base_url + "/"):
                raise BuildError(f"{path}: link to its own site must be root-relative: {href}")
