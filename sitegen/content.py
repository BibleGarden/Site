"""Loading and validating site configuration, translations and articles."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import markdown
import yaml
from markdown.extensions.toc import slugify_unicode
from markupsafe import Markup, escape

from .errors import BuildError

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
FAQ_HEADING_RE = re.compile(r"^## .*\{#faq\}\s*$")
H2_RE = re.compile(r"^## ")
H3_RE = re.compile(r"^### (.+?)\s*$")
LANGUAGE_RE = re.compile(r"^[a-z]{2}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

REQUIRED_SITE_KEYS = ("name", "base_url", "output_dir", "languages", "default_language", "language_labels", "logo", "author", "analytics")
AUTHOR_KEYS = {"name", "page"}
PAGE_PATH_RE = re.compile(r"^(?:[a-z0-9]+(?:-[a-z0-9]+)*/)?$")
APP_STORE_CAMPAIGN_PREFIX = "https://apps.apple.com/"
ANALYTICS_KEYS = {"script_url", "website_id"}
ANALYTICS_DISABLED = "none"
SOURCE_DIRS = ("content", "templates", "sitegen", ".git", ".github")
REQUIRED_ARTICLE_KEYS = ("title", "description", "date")
OPTIONAL_ARTICLE_KEYS = ("updated", "draft", "image")
PAGE_KEYS = ("title", "description")
MARKDOWN_EXTENSIONS = ["extra", "toc", "sane_lists"]
MARKDOWN_EXTENSION_CONFIGS = {"toc": {"slugify": slugify_unicode, "toc_depth": "2-3"}}


@dataclass(frozen=True)
class Analytics:
    """Umami tracker of a site: the script URL and the website ID created in Umami."""

    script_url: str
    website_id: str
    domain: str

    @property
    def script_tag(self) -> Markup:
        """The exact tag every page of the site carries.

        data-domains keeps local previews out of the stats; data-exclude-search and
        data-exclude-hash make the tracker drop query strings and fragments from the
        page and referrer URLs before sending them, so Umami never stores them.
        """
        return Markup(
            f'<script defer src="{escape(self.script_url)}" data-website-id="{escape(self.website_id)}"'
            f' data-domains="{escape(self.domain)}" data-exclude-search="true" data-exclude-hash="true"></script>'
        )


@dataclass(frozen=True)
class Author:
    """The author of every article of a site: an organization with a localized name and a page of the site."""

    name: dict[str, str]
    page: str

    def json_ld(self, site: Site, lang: str) -> dict:
        return {"@type": "Organization", "name": self.name[lang], "url": site.url(lang, self.page)}


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    base_url: str
    output_dir: Path
    languages: tuple[str, ...]
    default_language: str
    config: dict
    i18n: dict[str, dict]
    analytics: Analytics | None
    author: Author

    def language_prefix(self, lang: str) -> str:
        """URL path prefix for a language: '' for the default language, 'ru/' otherwise."""
        return "" if lang == self.default_language else f"{lang}/"

    def href(self, lang: str, path: str = "") -> str:
        """Root-relative link to a page, used for navigation inside the site."""
        return f"/{self.language_prefix(lang)}{path}"

    def url(self, lang: str, path: str = "") -> str:
        """Absolute URL of a page, used for canonical, hreflang, Open Graph, sitemap and JSON-LD."""
        return f"{self.base_url}{self.href(lang, path)}"

    def article_app_store_url(self, lang: str) -> str:
        """App Store link of the article pages: the campaign link of the page language (ct=seo-<lang>)."""
        template = self.config.get("article_app_store_url")
        if template is None:
            raise BuildError(f"{self.key}: site.yaml has no article_app_store_url, but a template uses it")
        return template.format(lang=lang)


@dataclass(frozen=True)
class FaqItem:
    question: str
    answer_html: str


@dataclass(frozen=True)
class Article:
    slug: str
    lang: str
    title: str
    description: str
    date: dt.date
    updated: dt.date | None
    draft: bool
    image: str | None
    body_html: str
    faq: tuple[FaqItem, ...]

    @property
    def path(self) -> str:
        return f"articles/{self.slug}/"


@dataclass(frozen=True)
class StaticPage:
    """A standalone page of a site, such as /about/: content/<site>/pages/<slug>/<lang>.md."""

    slug: str
    lang: str
    title: str
    description: str
    body_html: str

    @property
    def path(self) -> str:
        return f"{self.slug}/"


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise BuildError(f"{path}: expected a mapping at the top level")
    return data


def load_site(content_dir: Path, repo_root: Path) -> Site:
    config_path = content_dir / "site.yaml"
    config = load_yaml(config_path)
    missing = [key for key in REQUIRED_SITE_KEYS if key not in config]
    if missing:
        raise BuildError(f"{config_path}: missing required keys: {', '.join(missing)}")
    languages = tuple(config["languages"])
    if config["default_language"] not in languages:
        raise BuildError(f"{config_path}: default_language is not listed in languages")
    for lang in languages:
        if not isinstance(lang, str) or not LANGUAGE_RE.match(lang):
            raise BuildError(f"{config_path}: language codes must be two lowercase letters, got {lang!r}")
    if set(config["language_labels"]) != set(languages):
        raise BuildError(f"{config_path}: language_labels must define a label for every language and nothing else")
    if "article_app_store_url" in config:
        _article_app_store_url(config["article_app_store_url"], config_path)
    output_dir = _output_dir(config["output_dir"], repo_root, config_path)
    _check_owned_dirs(output_dir, languages, config["default_language"], repo_root, config_path)
    i18n = {lang: load_yaml(content_dir / "i18n" / f"{lang}.yaml") for lang in languages}
    reference = i18n[config["default_language"]]
    for lang in languages:
        _check_same_keys(reference, i18n[lang], f"{content_dir / 'i18n' / lang}.yaml", "")
    return Site(
        key=content_dir.name,
        name=config["name"],
        base_url=config["base_url"].rstrip("/"),
        output_dir=output_dir,
        languages=languages,
        default_language=config["default_language"],
        config=config,
        i18n=i18n,
        analytics=_analytics(config["analytics"], config["base_url"], config_path),
        author=_author(config["author"], languages, config_path),
    )


def _author(value: object, languages: tuple[str, ...], config_path: Path) -> Author:
    """Parse `author`: {name: {<lang>: name for every language}, page: '' (landing) or '<page slug>/'}."""
    if not isinstance(value, dict) or set(value) != AUTHOR_KEYS:
        raise BuildError(f"{config_path}: author must be a mapping with exactly {', '.join(sorted(AUTHOR_KEYS))}")
    name, page = value["name"], value["page"]
    if not isinstance(name, dict) or set(name) != set(languages) or not all(isinstance(text, str) and text.strip() for text in name.values()):
        raise BuildError(f"{config_path}: author.name must give a non-empty name for every language and nothing else")
    if not isinstance(page, str) or not PAGE_PATH_RE.match(page):
        raise BuildError(f"{config_path}: author.page must be '' (the landing page) or '<page slug>/', got {page!r}")
    return Author(name={lang: name[lang].strip() for lang in languages}, page=page)


def _article_app_store_url(value: object, config_path: Path) -> None:
    if not isinstance(value, str) or not value.startswith(APP_STORE_CAMPAIGN_PREFIX) or "{lang}" not in value:
        raise BuildError(f"{config_path}: article_app_store_url must be an {APP_STORE_CAMPAIGN_PREFIX} link with a {{lang}} placeholder, got {value!r}")


def _analytics(value: object, base_url: str, config_path: Path) -> Analytics | None:
    """Parse `analytics`: the explicit string 'none', or a mapping with script_url and website_id."""
    if value == ANALYTICS_DISABLED:
        return None
    if not isinstance(value, dict) or set(value) != ANALYTICS_KEYS:
        raise BuildError(f"{config_path}: analytics must be '{ANALYTICS_DISABLED}' or a mapping with exactly {', '.join(sorted(ANALYTICS_KEYS))}")
    script_url, website_id = value["script_url"], value["website_id"]
    if not isinstance(script_url, str) or urlsplit(script_url).scheme != "https" or not urlsplit(script_url).hostname:
        raise BuildError(f"{config_path}: analytics.script_url must be an https:// URL, got {script_url!r}")
    if not isinstance(website_id, str) or not UUID_RE.match(website_id):
        raise BuildError(f"{config_path}: analytics.website_id must be a lowercase UUID, got {website_id!r}")
    return Analytics(script_url=script_url, website_id=website_id, domain=urlsplit(base_url).hostname)


def _output_dir(value: object, repo_root: Path, config_path: Path) -> Path:
    """Resolve output_dir: a relative path inside the repository (the build deletes directories under it)."""
    if not isinstance(value, str) or not value:
        raise BuildError(f"{config_path}: output_dir must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise BuildError(f"{config_path}: output_dir must be relative to the repository root without '..': {value}")
    resolved = (repo_root / relative).resolve()
    if not resolved.is_relative_to(repo_root.resolve()):
        raise BuildError(f"{config_path}: output_dir resolves outside the repository: {resolved}")
    return resolved


def owned_dirs(output_dir: Path, languages: tuple[str, ...], default_language: str) -> list[Path]:
    """Directories the build deletes and recreates, normalised: articles/ and the non-default language roots."""
    return [(output_dir / name).resolve() for name in ["articles", *(lang for lang in languages if lang != default_language)]]


def _check_owned_dirs(output_dir: Path, languages: tuple[str, ...], default_language: str, repo_root: Path, config_path: Path) -> None:
    root = repo_root.resolve()
    protected = [(root / name).resolve() for name in SOURCE_DIRS]
    for owned in owned_dirs(output_dir, languages, default_language):
        if owned == root or not owned.is_relative_to(root):
            raise BuildError(f"{config_path}: the build would delete {owned}, which is not a directory inside the repository")
        for source in protected:
            if owned.is_relative_to(source) or source.is_relative_to(owned):
                raise BuildError(f"{config_path}: the build would delete {owned}, which overlaps the sources in {source}")


def _check_same_keys(reference: dict, candidate: dict, path: str, prefix: str) -> None:
    ref_keys, cand_keys = set(reference), set(candidate)
    if ref_keys != cand_keys:
        missing = sorted(prefix + key for key in ref_keys - cand_keys)
        extra = sorted(prefix + key for key in cand_keys - ref_keys)
        raise BuildError(f"{path}: translation keys differ from the default language; missing {missing}, extra {extra}")
    for key, value in reference.items():
        if hasattr(dict, key):
            raise BuildError(f"{path}: key {prefix + key} shadows a dict method in templates; rename it")
        if isinstance(value, dict):
            if not isinstance(candidate[key], dict):
                raise BuildError(f"{path}: key {prefix + key} must be a mapping")
            _check_same_keys(value, candidate[key], path, f"{prefix}{key}.")
        elif not isinstance(candidate[key], str):
            raise BuildError(f"{path}: key {prefix + key} must be a string")


def load_articles(site: Site, content_dir: Path) -> dict[str, dict[str, Article]]:
    """Return {slug: {lang: Article}} for every article directory of the site."""
    articles_dir = content_dir / "articles"
    result: dict[str, dict[str, Article]] = {}
    if not articles_dir.is_dir():
        raise BuildError(f"{articles_dir}: missing articles directory (keep it, even if empty, with a .gitkeep)")
    for slug_dir in sorted(articles_dir.iterdir()):
        if slug_dir.name == ".gitkeep":
            continue
        if not slug_dir.is_dir():
            raise BuildError(f"{slug_dir}: only <slug>/ directories are allowed under articles/")
        if not SLUG_RE.match(slug_dir.name):
            raise BuildError(f"{slug_dir}: slug must be lowercase latin letters, digits and hyphens")
        versions: dict[str, Article] = {}
        for source in sorted(slug_dir.iterdir()):
            if source.suffix != ".md":
                raise BuildError(f"{source}: only <lang>.md files are allowed in an article directory")
            lang = source.stem
            if lang not in site.languages:
                raise BuildError(f"{source}: unknown language '{lang}', expected one of {', '.join(site.languages)}")
            versions[lang] = parse_article(source, slug_dir.name, lang)
        if not versions:
            raise BuildError(f"{slug_dir}: article directory has no language versions")
        result[slug_dir.name] = versions
    return result


def load_pages(site: Site, content_dir: Path) -> dict[str, dict[str, StaticPage]]:
    """Return {slug: {lang: StaticPage}} for content/<site>/pages/<slug>/<lang>.md; a site may have no pages/ directory."""
    pages_dir = content_dir / "pages"
    result: dict[str, dict[str, StaticPage]] = {}
    if not pages_dir.is_dir():
        return result
    reserved = {"articles", *site.languages}
    for slug_dir in sorted(pages_dir.iterdir()):
        if not slug_dir.is_dir():
            raise BuildError(f"{slug_dir}: only <slug>/ directories are allowed under pages/")
        if not SLUG_RE.match(slug_dir.name) or slug_dir.name in reserved:
            raise BuildError(f"{slug_dir}: page slug must be lowercase latin letters, digits and hyphens, and not one of {', '.join(sorted(reserved))}")
        versions: dict[str, StaticPage] = {}
        for source in sorted(slug_dir.iterdir()):
            if source.suffix != ".md" or source.stem not in site.languages:
                raise BuildError(f"{source}: only <lang>.md files for {', '.join(site.languages)} are allowed in a page directory")
            meta, body = _frontmatter(source, PAGE_KEYS, ())
            versions[source.stem] = StaticPage(
                slug=slug_dir.name,
                lang=source.stem,
                title=_require_str(meta, "title", source),
                description=_require_str(meta, "description", source),
                body_html=render_markdown(body),
            )
        if not versions:
            raise BuildError(f"{slug_dir}: page directory has no language versions")
        result[slug_dir.name] = versions
    return result


def _frontmatter(source: Path, required: tuple[str, ...], optional: tuple[str, ...]) -> tuple[dict, str]:
    """Split a Markdown source into its validated frontmatter mapping and body."""
    text = source.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise BuildError(f"{source}: missing YAML frontmatter delimited by '---' lines")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise BuildError(f"{source}: frontmatter must be a mapping")
    missing = [key for key in required if key not in meta]
    if missing:
        raise BuildError(f"{source}: missing required frontmatter keys: {', '.join(missing)}")
    unknown = sorted(set(meta) - set(required) - set(optional))
    if unknown:
        raise BuildError(f"{source}: unknown frontmatter keys: {', '.join(unknown)}")
    return meta, match.group(2)


def parse_article(source: Path, slug: str, lang: str) -> Article:
    meta, body = _frontmatter(source, REQUIRED_ARTICLE_KEYS, OPTIONAL_ARTICLE_KEYS)
    return Article(
        slug=slug,
        lang=lang,
        title=_require_str(meta, "title", source),
        description=_require_str(meta, "description", source),
        date=_require_date(meta, "date", source),
        updated=_require_date(meta, "updated", source) if "updated" in meta else None,
        draft=_require_bool(meta, "draft", source) if "draft" in meta else False,
        image=_require_str(meta, "image", source) if "image" in meta else None,
        body_html=render_markdown(body),
        faq=extract_faq(body, source),
    )


def _require_str(meta: dict, key: str, source: Path) -> str:
    value = meta[key]
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{source}: frontmatter key '{key}' must be a non-empty string")
    return value.strip()


def _require_date(meta: dict, key: str, source: Path) -> dt.date:
    value = meta[key]
    if not isinstance(value, dt.date) or isinstance(value, dt.datetime):
        raise BuildError(f"{source}: frontmatter key '{key}' must be a date like 2026-09-21")
    return value


def _require_bool(meta: dict, key: str, source: Path) -> bool:
    value = meta[key]
    if not isinstance(value, bool):
        raise BuildError(f"{source}: frontmatter key '{key}' must be true or false")
    return value


def render_markdown(text: str) -> str:
    return markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS, extension_configs=MARKDOWN_EXTENSION_CONFIGS)


def extract_faq(body: str, source: Path) -> tuple[FaqItem, ...]:
    """Collect '### question' / answer pairs from the '## ... {#faq}' section, if present."""
    lines = body.splitlines()
    fenced = _fenced_flags(lines)

    def heading(index: int, pattern: re.Pattern[str]) -> re.Match[str] | None:
        return None if fenced[index] else pattern.match(lines[index])

    starts = [index for index in range(len(lines)) if heading(index, FAQ_HEADING_RE)]
    if not starts:
        return ()
    if len(starts) > 1:
        raise BuildError(f"{source}: only one '{{#faq}}' section is allowed")
    end = next((index for index in range(starts[0] + 1, len(lines)) if heading(index, H2_RE)), len(lines))
    items: list[FaqItem] = []
    question: str | None = None
    answer: list[str] = []

    def flush() -> None:
        if question is None:
            return
        answer_text = "\n".join(answer).strip()
        if not answer_text:
            raise BuildError(f"{source}: FAQ question '{question}' has no answer")
        items.append(FaqItem(question=question, answer_html=render_markdown(answer_text)))

    for index in range(starts[0] + 1, end):
        match = heading(index, H3_RE)
        if match:
            flush()
            question, answer = match.group(1), []
        elif question is None and lines[index].strip():
            raise BuildError(f"{source}: FAQ section must start with a '### question' heading")
        else:
            answer.append(lines[index])
    flush()
    if not items:
        raise BuildError(f"{source}: FAQ section has no '### question' entries")
    return tuple(items)


FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _fenced_flags(lines: list[str]) -> list[bool]:
    """Whether each line sits inside a fenced code block, fence lines included (CommonMark rules).

    An opening fence is 3+ backticks or tildes indented by at most 3 spaces (a backtick fence
    has no backtick in its info string); it closes with the same character, at least as long,
    followed only by spaces.
    """
    flags: list[bool] = []
    fence: str | None = None
    for line in lines:
        match = FENCE_RE.match(line)
        if fence is None:
            if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
                fence = match.group(1)
                flags.append(True)
            else:
                flags.append(False)
        else:
            flags.append(True)
            marker = match.group(1) if match else ""
            if match and marker[0] == fence[0] and len(marker) >= len(fence) and not match.group(2).strip():
                fence = None
    return flags
