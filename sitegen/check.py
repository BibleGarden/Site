"""Validation of the HTML pages: JSON-LD contents, hreflang targets, internal links and analytics."""

from __future__ import annotations

import json
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree import ElementTree

from .build import CONTENT_DIR, PUBLIC_DIR, REPO_ROOT, build_all
from .content import Site, load_site
from .errors import BuildError
from .screens import ASSET_DIR, VARIANTS, check_asset, load_catalog, load_checksums

JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)">')
HREFLANG_RE = re.compile(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">')
HTML_LANG_RE = re.compile(r'<html lang="([^"]+)"')
NOINDEX_RE = re.compile(r'<meta name="robots" content="noindex">')
ANCHOR_HREF_RE = re.compile(r'<a\s[^>]*?href="([^"]+)"')
APP_STORE_PREFIX = "https://apps.apple.com/"
APP_STORE_EVENT = "app-store-click"


def html_files() -> list[Path]:
    return sorted(PUBLIC_DIR.rglob("*.html"))


def check_build_output() -> None:
    """Require the committed public tree to match a clean build byte for byte."""
    with tempfile.TemporaryDirectory() as directory:
        expected = Path(directory) / "sites"
        build_all(output_root=expected)
        expected_files = {path.relative_to(expected): path for path in expected.rglob("*") if path.is_file()}
        actual_files = {path.relative_to(PUBLIC_DIR): path for path in PUBLIC_DIR.rglob("*") if path.is_file()}
        if expected_files.keys() != actual_files.keys():
            raise BuildError(f"dist differs from source: missing={sorted(expected_files.keys() - actual_files.keys())}, extra={sorted(actual_files.keys() - expected_files.keys())}")
        for relative, source in expected_files.items():
            if source.read_bytes() != actual_files[relative].read_bytes():
                raise BuildError(f"dist differs from source: {relative}")


def run_checks() -> tuple[int, int]:
    """Return (JSON-LD blocks, hreflang links) after validating every generated HTML file."""
    for name in ("index.html", "404.html", "robots.txt", "sitemap.xml", "llms.txt", "privacy.html",
                 "about", "articles", "ru", "uk", "css", "js", "img", "lampada"):
        if (REPO_ROOT / name).exists():
            raise BuildError(f"legacy public path remains outside dist: {name}")
    check_build_output()
    sites = [load_site(directory, REPO_ROOT) for directory in sorted(CONTENT_DIR.iterdir()) if directory.is_dir()]
    pages = {path: path.read_text(encoding="utf-8") for path in html_files()}
    check_public_references(pages, sites)
    owners = {path: owner_site(path, sites) for path in pages}
    blocks = sum(check_json_ld(path, html) for path, html in pages.items())
    links = check_hreflang(pages, sites)
    check_internal_links(pages, owners)
    check_analytics(pages, owners)
    check_screens(sites)
    return blocks, links


class ReferenceCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is None:
                continue
            if name in {"href", "src", "poster"}:
                self.references.append(value)
            elif name == "srcset":
                self.references.extend(part.strip().split()[0] for part in value.split(","))
            elif name == "content" and value.startswith(("/", "https://bible.garden/", "https://lampada.app/")):
                self.references.append(value)


def check_public_references(pages: dict[Path, str], sites: list[Site]) -> None:
    """Every local URL in published pages and discovery files must resolve inside dist."""
    def require(reference: str, base_url: str, source: Path) -> None:
        if not reference or unquote(reference).startswith(("#", "data:")):
            return
        url = urlsplit(urljoin(base_url, reference))
        if url.scheme not in {"http", "https"}:
            return
        for site in sites:
            if url.netloc == urlsplit(site.base_url).netloc:
                clean_url = f"{site.base_url}{unquote(url.path or '/')}"
                if url_to_file(clean_url, sites) is None:
                    raise BuildError(f"{source}: missing public reference {reference}")
                return

    for path, html in pages.items():
        owner = owner_site(path, sites)
        relative = path.relative_to(owner.output_dir).as_posix()
        parser = ReferenceCollector()
        parser.feed(html)
        for reference in parser.references:
            require(reference, f"{owner.base_url}/{relative}", path)

    for site in sites:
        for path in site.output_dir.rglob("*.css"):
            relative = path.relative_to(site.output_dir).as_posix()
            for reference in re.findall(r"url\(['\"]?([^)'\"]+)", path.read_text(encoding="utf-8")):
                require(reference, f"{site.base_url}/{relative}", path)
        sitemap = site.output_dir / "sitemap.xml"
        for element in ElementTree.parse(sitemap).iter():
            if element.tag.endswith("loc") and element.text:
                require(element.text, site.base_url + "/", sitemap)
            if element.tag.endswith("link") and "href" in element.attrib:
                require(element.attrib["href"], site.base_url + "/", sitemap)
        for name in ("llms.txt", "robots.txt"):
            path = site.output_dir / name
            for reference in re.findall(r"https?://[^\s)]+", path.read_text(encoding="utf-8")):
                require(reference, site.base_url + "/", path)
        if not (site.output_dir / "404.html").is_file():
            raise BuildError(f"{site.output_dir}: missing 404.html")


def check_screens(sites: list[Site]) -> None:
    """The archive stays outside git, so CI verifies every committed variant."""
    for site in sites:
        catalog = load_catalog(CONTENT_DIR / site.key / "screens.yaml", site.languages)
        if not catalog:
            continue
        checksums = load_checksums(CONTENT_DIR / site.key / "screens.sha256", catalog, site.languages)
        expected = {screen.path(lang, variant) for screen in catalog.values() for lang in site.languages for variant in VARIANTS}
        for screen in catalog.values():
            for lang in site.languages:
                for variant in VARIANTS:
                    check_asset(screen, lang, variant, site.output_dir, checksums[screen.path(lang, variant)])
        actual = {path.relative_to(site.output_dir) for path in (site.output_dir / ASSET_DIR).rglob("*") if path.is_file()}
        if actual != expected:
            raise BuildError(f"{site.output_dir / ASSET_DIR}: unexpected screenshot assets: {sorted(actual - expected)}")


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
        elif kind in ("AboutPage", "WebPage"):
            _require(path, data, "name", "description", "url", "inLanguage")
            if kind == "AboutPage":
                _require_organization(path, data.get("mainEntity"))
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
