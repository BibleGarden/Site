"""Loading and validating site configuration, translations and articles."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import markdown
import yaml
from markdown.extensions.toc import slugify_unicode

from .errors import BuildError

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
FAQ_HEADING_RE = re.compile(r"^## .*\{#faq\}\s*$")
H2_RE = re.compile(r"^## ")
H3_RE = re.compile(r"^### (.+?)\s*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

REQUIRED_SITE_KEYS = ("name", "base_url", "output_dir", "languages", "default_language", "logo")
REQUIRED_ARTICLE_KEYS = ("title", "description", "date", "author")
OPTIONAL_ARTICLE_KEYS = ("updated", "draft", "image")
MARKDOWN_EXTENSIONS = ["extra", "toc", "sane_lists"]
MARKDOWN_EXTENSION_CONFIGS = {"toc": {"slugify": slugify_unicode, "toc_depth": "2-3"}}


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

    def language_prefix(self, lang: str) -> str:
        """URL path prefix for a language: '' for the default language, 'ru/' otherwise."""
        return "" if lang == self.default_language else f"{lang}/"

    def url(self, lang: str, path: str = "") -> str:
        return f"{self.base_url}/{self.language_prefix(lang)}{path}"


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
    author: str
    draft: bool
    image: str | None
    body_html: str
    faq: tuple[FaqItem, ...]

    @property
    def path(self) -> str:
        return f"articles/{self.slug}/"


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
    i18n = {lang: load_yaml(content_dir / "i18n" / f"{lang}.yaml") for lang in languages}
    reference = i18n[config["default_language"]]
    for lang in languages:
        _check_same_keys(reference, i18n[lang], f"{content_dir / 'i18n' / lang}.yaml", "")
    return Site(
        key=content_dir.name,
        name=config["name"],
        base_url=config["base_url"].rstrip("/"),
        output_dir=(repo_root / config["output_dir"]).resolve(),
        languages=languages,
        default_language=config["default_language"],
        config=config,
        i18n=i18n,
    )


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
    if not articles_dir.exists():
        return result
    for slug_dir in sorted(articles_dir.iterdir()):
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


def parse_article(source: Path, slug: str, lang: str) -> Article:
    text = source.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise BuildError(f"{source}: missing YAML frontmatter delimited by '---' lines")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise BuildError(f"{source}: frontmatter must be a mapping")
    missing = [key for key in REQUIRED_ARTICLE_KEYS if key not in meta]
    if missing:
        raise BuildError(f"{source}: missing required frontmatter keys: {', '.join(missing)}")
    unknown = sorted(set(meta) - set(REQUIRED_ARTICLE_KEYS) - set(OPTIONAL_ARTICLE_KEYS))
    if unknown:
        raise BuildError(f"{source}: unknown frontmatter keys: {', '.join(unknown)}")
    body = match.group(2)
    return Article(
        slug=slug,
        lang=lang,
        title=_require_str(meta, "title", source),
        description=_require_str(meta, "description", source),
        date=_require_date(meta, "date", source),
        updated=_require_date(meta, "updated", source) if "updated" in meta else None,
        author=_require_str(meta, "author", source),
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


def _fenced_flags(lines: list[str]) -> list[bool]:
    """Whether each line sits inside a ``` fenced code block (fence lines count as inside)."""
    flags: list[bool] = []
    fenced = False
    for line in lines:
        if line.startswith("```"):
            fenced = not fenced
            flags.append(True)
        else:
            flags.append(fenced)
    return flags
