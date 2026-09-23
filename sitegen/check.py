"""Validation of the HTML pages: JSON-LD contents, hreflang targets, internal links and analytics."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from .build import CONTENT_DIR, REPO_ROOT
from .content import Site, load_site
from .errors import BuildError

JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)">')
HREFLANG_RE = re.compile(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">')
HTML_LANG_RE = re.compile(r'<html lang="([^"]+)"')
NOINDEX_RE = re.compile(r'<meta name="robots" content="noindex">')
ANCHOR_HREF_RE = re.compile(r'<a\s[^>]*?href="([^"]+)"')
APP_STORE_PREFIX = "https://apps.apple.com/"
APP_STORE_EVENT = "app-store-click"
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
    check_analytics(pages, owners)
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
            _require_organization(path, data.get("author"))
            _require(path, data["publisher"], "name", "logo")
        elif kind in ("AboutPage", "WebPage", "ProfilePage"):
            _require(path, data, "name", "description", "url", "inLanguage")
            if kind == "AboutPage":
                _require_organization(path, data.get("mainEntity"))
            elif kind == "ProfilePage":
                _require_person(path, data.get("mainEntity"))
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


def _require_organization(path: Path, data: object) -> None:
    """Article author and AboutPage subject: the organization whose page explains how the texts are written."""
    _require(path, data, "name", "url")
    if data.get("@type") != "Organization":
        raise BuildError(f"{path}: JSON-LD author (or AboutPage mainEntity) must be an Organization, got {data.get('@type')!r}")


def _require_person(path: Path, data: object) -> None:
    """A ProfilePage's mainEntity: the person, optionally with the Organization they work for."""
    _require(path, data, "name", "url")
    if data.get("@type") != "Person":
        raise BuildError(f"{path}: JSON-LD ProfilePage mainEntity must be a Person, got {data.get('@type')!r}")
    works_for = data.get("worksFor")
    if works_for is not None:
        _require_organization(path, works_for)


def _require_list(path: Path, data: dict, key: str) -> None:
    if not isinstance(data.get(key), list) or not data[key]:
        raise BuildError(f"{path}: JSON-LD field {key!r} must be a non-empty list")


def check_hreflang(pages: dict[Path, str], sites: list[Site]) -> int:
    """canonical and hreflang consistency across all pages.

    Every indexable page has a canonical URL that resolves to the page itself. A page with
    hreflang links lists every published version (itself included) plus x-default, each
    target is an indexable page whose <html lang> matches the tag and whose canonical is the
    linked URL, and every version lists the same set.
    """
    def resolve(path: Path, url: str, what: str) -> Path:
        target = url_to_file(url, sites)
        if target is None:
            raise BuildError(f"{path}: {what} points at a page that does not exist: {url}")
        return target.resolve()

    info: dict[Path, tuple[str | None, bool, str | None, dict[str, str]]] = {}
    for path, html in pages.items():
        canonicals = CANONICAL_RE.findall(html)
        if len(canonicals) > 1:
            raise BuildError(f"{path}: more than one canonical link")
        tags = HREFLANG_RE.findall(html)
        codes = [code for code, _ in tags]
        duplicates = sorted({code for code in codes if codes.count(code) > 1})
        if duplicates:
            raise BuildError(f"{path}: duplicate hreflang for {', '.join(duplicates)}")
        html_lang = HTML_LANG_RE.search(html)
        info[path.resolve()] = (
            canonicals[0] if canonicals else None,
            bool(NOINDEX_RE.search(html)),
            html_lang.group(1) if html_lang else None,
            dict(tags),
        )

    links = 0
    for path, (canonical, noindex, _, alternates) in info.items():
        if canonical is not None and resolve(path, canonical, "canonical") != path:
            raise BuildError(f"{path}: canonical {canonical} does not resolve to the page itself")
        if noindex:
            if alternates:
                raise BuildError(f"{path}: a noindex page must not carry hreflang links")
            continue
        if canonical is None:
            raise BuildError(f"{path}: indexable page has no canonical link")
        expected = {version for version in language_versions(path, sites) if not info[version][1]}
        linked = {resolve(path, url, f"hreflang {code}") for code, url in alternates.items() if code != "x-default"}
        if len(expected) > 1 and linked != expected:
            missing = sorted(str(version) for version in expected - linked)
            raise BuildError(f"{path}: hreflang must list every indexable language version; missing or extra: {missing or sorted(map(str, linked - expected))}")
        if not alternates:
            continue
        versions = {code: url for code, url in alternates.items() if code != "x-default"}
        if "x-default" not in alternates:
            raise BuildError(f"{path}: hreflang set has no x-default")
        if alternates["x-default"] not in versions.values():
            raise BuildError(f"{path}: x-default {alternates['x-default']} is not one of the language versions")
        if canonical not in versions.values():
            raise BuildError(f"{path}: hreflang set does not include the page itself")
        for code, url in versions.items():
            target_canonical, target_noindex, target_lang, target_alternates = info[resolve(path, url, f"hreflang {code}")]
            if target_noindex:
                raise BuildError(f"{path}: hreflang {code} points at a noindex page {url}")
            if target_lang != code:
                raise BuildError(f"{path}: hreflang {code} points at a page with <html lang={target_lang!r}>: {url}")
            if target_canonical != url:
                raise BuildError(f"{path}: hreflang {code} {url} is not the canonical URL of its target ({target_canonical})")
            if target_alternates != alternates:
                raise BuildError(f"{path}: hreflang set differs from the one on {url}")
            links += 1
    return links


def language_versions(path: Path, sites: list[Site]) -> set[Path]:
    """Files that are the same page under every language prefix of its site, found on disk.

    The page's language comes from its first path segment (a non-default language) or is the
    default one; the same remaining path under each other prefix is a version if it exists.
    """
    site = owner_site(path, sites)
    parts = path.relative_to(site.output_dir).parts
    prefixed = [lang for lang in site.languages if lang != site.default_language]
    rest = parts[1:] if parts[0] in prefixed else parts
    versions = set()
    for lang in site.languages:
        candidate = site.output_dir.joinpath(*([] if lang == site.default_language else [lang]), *rest)
        if candidate.is_file():
            versions.add(candidate.resolve())
    return versions


def check_internal_links(pages: dict[Path, str], owners: dict[Path, Site]) -> None:
    """Navigation inside a site must be root-relative so previews stay on the preview host."""
    for path, html in pages.items():
        base_url = owners[path].base_url
        for href in ANCHOR_HREF_RE.findall(html):
            if href == base_url or href.startswith(base_url + "/"):
                raise BuildError(f"{path}: link to its own site must be root-relative: {href}")


class TagCollector(HTMLParser):
    """<script> and <a> start tags of a page as attribute dicts; the parser lower-cases tag and attribute names."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[dict[str, str]] = []
        self.anchors: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "a"):
            (self.scripts if tag == "script" else self.anchors).append({name: value or "" for name, value in attrs})


def is_tracker(attrs: dict[str, str], tracker_hosts: set[str]) -> bool:
    """A <script> that loads Umami: a website ID, Umami's /script.js, or a src on a configured tracker host."""
    if "data-website-id" in attrs:
        return True
    src = attrs.get("src", "").strip()
    if not src:
        return False
    url = urlsplit(src)
    return url.path.lower().endswith("/script.js") or "umami" in src.lower() or (url.hostname or "") in tracker_hosts


def check_analytics(pages: dict[Path, str], owners: dict[Path, Site]) -> None:
    """Every page, hand-written ones included, carries its site's tracker exactly once, or no tracker at all when
    analytics is 'none'; every App Store link reports the app-store-click event."""
    tracker_hosts = {urlsplit(site.analytics.script_url).hostname for site in owners.values() if site.analytics}
    for path, html in pages.items():
        analytics = owners[path].analytics
        tags = TagCollector()
        tags.feed(html)
        tags.close()
        trackers = sum(is_tracker(attrs, tracker_hosts) for attrs in tags.scripts)
        if analytics is None:
            if trackers:
                raise BuildError(f"{path}: analytics is 'none' in site.yaml, but the page has a tracker script")
        elif trackers != 1 or html.count(analytics.script_tag) != 1:
            raise BuildError(f"{path}: the page must carry exactly one tracker, and it must be {analytics.script_tag}")
        for attrs in tags.anchors:
            href = attrs.get("href", "").strip()
            if href.lower().startswith(APP_STORE_PREFIX) and attrs.get("data-umami-event") != APP_STORE_EVENT:
                raise BuildError(f'{path}: App Store link {href} without data-umami-event="{APP_STORE_EVENT}"')
