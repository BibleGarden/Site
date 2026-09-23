"""Validation of the generated HTML: JSON-LD contents and hreflang targets."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .build import CONTENT_DIR, REPO_ROOT
from .content import Site, load_site
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
    sites = [load_site(directory, REPO_ROOT) for directory in sorted(CONTENT_DIR.iterdir()) if directory.is_dir()]
    pages = {path: path.read_text(encoding="utf-8") for path in html_files()}
    owners = {path: owner_site(path, sites) for path in pages}
    blocks = sum(check_json_ld(path, html) for path, html in pages.items())
    links = check_hreflang(pages, sites)
    check_internal_links(pages, owners)
    return blocks, links


def owner_site(path: Path, sites: list[Site]) -> Site:
    """The site whose output directory most specifically contains the page (lampada/ is nested in the root)."""
    return max((site for site in sites if path.is_relative_to(site.output_dir)), key=lambda site: len(site.output_dir.parts))


def url_to_file(url: str, sites: list[Site]) -> Path | None:
    """The file nginx serves for an absolute URL of one of the sites, or None if there is none."""
    for site in sites:
        if url.startswith(site.base_url + "/"):
            relative = url[len(site.base_url) + 1 :]
            candidates = [site.output_dir / relative / "index.html"] if relative.endswith("/") or not relative else [
                site.output_dir / relative,
                site.output_dir / relative / "index.html",
            ]
            return next((candidate for candidate in candidates if candidate.is_file()), None)
    return None


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


def check_hreflang(pages: dict[Path, str], sites: list[Site]) -> int:
    """canonical and hreflang must point at generated files; hreflang never at a noindex page."""
    noindex_urls = {
        CANONICAL_RE.search(html).group(1)
        for html in pages.values()
        if NOINDEX_RE.search(html) and CANONICAL_RE.search(html)
    }
    links = 0
    for path, html in pages.items():
        for href in CANONICAL_RE.findall(html):
            if url_to_file(href, sites) is None:
                raise BuildError(f"{path}: canonical points at a page that does not exist: {href}")
        for href in HREFLANG_RE.findall(html):
            if url_to_file(href, sites) is None:
                raise BuildError(f"{path}: hreflang points at a page that does not exist: {href}")
            if href in noindex_urls:
                raise BuildError(f"{path}: hreflang points at a noindex page {href}")
            links += 1
    return links


def check_internal_links(pages: dict[Path, str], owners: dict[Path, Site]) -> None:
    """Navigation inside a site must be root-relative so previews stay on the preview host."""
    for path, html in pages.items():
        base_url = owners[path].base_url
        for href in ANCHOR_HREF_RE.findall(html):
            if href == base_url or href.startswith(base_url + "/"):
                raise BuildError(f"{path}: link to its own site must be root-relative: {href}")
