"""Rendering pages, sitemaps and text files for every site."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape as html_escape

from .content import Article, Site, load_articles, load_site
from .errors import BuildError

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content"
TEMPLATES_DIR = REPO_ROOT / "templates"


@dataclass(frozen=True)
class Page:
    lang: str
    path: str
    title: str
    description: str
    alternates: dict[str, str]
    image: str
    og_type: str = "website"
    noindex: bool = False

    @property
    def canonical(self) -> str:
        return self.alternates[self.lang]


def nl2br(value: str) -> Markup:
    return Markup("<br>".join(html_escape(line) for line in value.split("\n")))


def jsonld(value: object) -> Markup:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)
    return Markup(text.replace("</", "<\\/"))


def make_environment(site_key: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader([TEMPLATES_DIR / site_key, TEMPLATES_DIR / "_shared"]),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["nl2br"] = nl2br
    env.filters["jsonld"] = jsonld
    return env


def discover_sites() -> list[Path]:
    sites = sorted(path.parent for path in CONTENT_DIR.glob("*/site.yaml"))
    if not sites:
        raise BuildError(f"no content/<site>/site.yaml found under {CONTENT_DIR}")
    return sites


def build_all() -> list[Path]:
    written: list[Path] = []
    for content_dir in discover_sites():
        written.extend(SiteBuilder(content_dir).build())
    return written


class SiteBuilder:
    def __init__(self, content_dir: Path) -> None:
        self.site = load_site(content_dir, REPO_ROOT)
        self.articles = load_articles(self.site, content_dir)
        self.env = make_environment(content_dir.name)
        self.written: list[Path] = []

    # --- helpers -----------------------------------------------------------------

    def t(self, lang: str) -> dict:
        return self.site.i18n[lang]

    def absolute(self, path: str) -> str:
        """Absolute URL for a site-root path such as '/img/logo.png'."""
        if not path.startswith("/"):
            raise BuildError(f"{self.site.key}: asset path must start with '/': {path}")
        return f"{self.site.base_url}{path}"

    def output_path(self, lang: str, path: str) -> Path:
        return self.site.output_dir / self.site.language_prefix(lang) / path

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.written.append(path)

    def render(self, template: str, path: Path, **context: object) -> None:
        self.write(path, self.env.get_template(template).render(site=self.site, **context))

    def published(self, lang: str) -> list[Article]:
        """Non-draft articles in a language, oldest first."""
        versions = [article[lang] for article in self.articles.values() if lang in article and not article[lang].draft]
        return sorted(versions, key=lambda article: (article.date, article.slug))

    def article_alternates(self, slug: str) -> dict[str, str]:
        return {lang: self.site.url(lang, self.articles[slug][lang].path) for lang in self.site.languages if lang in self.articles[slug]}

    # --- build steps --------------------------------------------------------------

    def build(self) -> list[Path]:
        self.clean()
        for lang in self.site.languages:
            self.build_landing(lang)
            self.build_articles_index(lang)
            for slug in self.articles:
                if lang in self.articles[slug]:
                    self.build_article(slug, lang)
        self.build_not_found()
        self.build_robots()
        self.build_sitemap()
        self.build_llms()
        return self.written

    def clean(self) -> None:
        """Remove every directory the generator owns so deleted content disappears from the output."""
        owned = [self.site.output_dir / "articles"]
        owned += [self.site.output_dir / lang for lang in self.site.languages if lang != self.site.default_language]
        for directory in owned:
            if directory.exists():
                shutil.rmtree(directory)

    def build_landing(self, lang: str) -> None:
        meta = self.t(lang)["meta"]
        page = Page(
            lang=lang,
            path="",
            title=meta["title"],
            description=meta["description"],
            alternates={other: self.site.url(other) for other in self.site.languages},
            image=self.absolute(self.site.config["logo"]),
        )
        self.render(
            "landing.html",
            self.output_path(lang, "index.html"),
            page=page,
            lang=lang,
            t=self.t(lang),
            has_articles=bool(self.published(lang)),
            lang_paths={other: f"/{self.site.language_prefix(other)}" for other in self.site.languages},
        )

    def build_articles_index(self, lang: str) -> None:
        strings = self.t(lang)["articles"]
        articles = self.published(lang)
        page = Page(
            lang=lang,
            path="articles/",
            title=strings["index_title"],
            description=strings["index_description"],
            alternates={other: self.site.url(other, "articles/") for other in self.site.languages},
            image=self.absolute(self.site.config["logo"]),
            noindex=not articles,
        )
        self.render(
            "articles.html",
            self.output_path(lang, "articles/index.html"),
            page=page,
            lang=lang,
            t=self.t(lang),
            articles=list(reversed(articles)),
        )

    def build_article(self, slug: str, lang: str) -> None:
        article = self.articles[slug][lang]
        neighbours = self.published(lang)
        previous = following = None
        if not article.draft:
            index = neighbours.index(article)
            previous = neighbours[index - 1] if index > 0 else None
            following = neighbours[index + 1] if index + 1 < len(neighbours) else None
        page = Page(
            lang=lang,
            path=article.path,
            title=f"{article.title} — {self.site.name}",
            description=article.description,
            alternates=self.article_alternates(slug),
            image=self.absolute(article.image or self.site.config["logo"]),
            og_type="article",
            noindex=article.draft,
        )
        self.render(
            "article.html",
            self.output_path(lang, f"{article.path}index.html"),
            page=page,
            lang=lang,
            t=self.t(lang),
            article=article,
            previous=previous,
            following=following,
            json_ld=self.article_json_ld(article, page),
        )

    def article_json_ld(self, article: Article, page: Page) -> list[dict]:
        strings = self.t(article.lang)["articles"]
        data: list[dict] = [
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "mainEntityOfPage": {"@type": "WebPage", "@id": page.canonical},
                "headline": article.title,
                "description": article.description,
                "image": [page.image],
                "inLanguage": article.lang,
                "datePublished": article.date.isoformat(),
                "dateModified": (article.updated or article.date).isoformat(),
                "author": {"@type": "Person", "name": article.author},
                "publisher": {
                    "@type": "Organization",
                    "name": self.site.name,
                    "url": self.site.base_url + "/",
                    "logo": {"@type": "ImageObject", "url": self.absolute(self.site.config["logo"])},
                },
            },
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": strings["breadcrumb_home"], "item": self.site.url(article.lang)},
                    {"@type": "ListItem", "position": 2, "name": strings["section_title"], "item": self.site.url(article.lang, "articles/")},
                    {"@type": "ListItem", "position": 3, "name": article.title, "item": page.canonical},
                ],
            },
        ]
        if article.faq:
            data.append(
                {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": item.question,
                            "acceptedAnswer": {"@type": "Answer", "text": item.answer_html},
                        }
                        for item in article.faq
                    ],
                }
            )
        return data

    def build_not_found(self) -> None:
        lang = self.site.default_language
        strings = self.t(lang)["not_found"]
        page = Page(
            lang=lang,
            path="404.html",
            title=f"{strings['title']} — {self.site.name}",
            description=strings["text"],
            alternates={lang: self.site.url(lang, "404.html")},
            image=self.absolute(self.site.config["logo"]),
            noindex=True,
        )
        self.render(
            "404.html",
            self.site.output_dir / "404.html",
            page=page,
            lang=lang,
            t=self.t(lang),
            homes=[(other, self.t(other)["meta"]["language_name"], self.site.url(other)) for other in self.site.languages],
        )

    def build_robots(self) -> None:
        lines = ["User-agent: *", "Allow: /"]
        lines += [f"Disallow: {path}" for path in self.site.config.get("robots_disallow", [])]
        lines += ["", f"Sitemap: {self.site.base_url}/sitemap.xml", ""]
        self.write(self.site.output_dir / "robots.txt", "\n".join(lines))

    def sitemap_entries(self) -> list[tuple[str, dict[str, str], str | None]]:
        """(url, alternates, lastmod) for every indexable page, in a stable order."""
        entries: list[tuple[str, dict[str, str], str | None]] = []
        landing = {lang: self.site.url(lang) for lang in self.site.languages}
        for lang in self.site.languages:
            entries.append((landing[lang], landing, None))
        index_langs = [lang for lang in self.site.languages if self.published(lang)]
        index = {lang: self.site.url(lang, "articles/") for lang in index_langs}
        for lang in index_langs:
            entries.append((index[lang], index, None))
        for slug in self.articles:
            alternates = {
                lang: url for lang, url in self.article_alternates(slug).items() if not self.articles[slug][lang].draft
            }
            for lang, url in alternates.items():
                article = self.articles[slug][lang]
                entries.append((url, alternates, (article.updated or article.date).isoformat()))
        return entries

    def build_sitemap(self) -> None:
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
        ]
        for url, alternates, lastmod in self.sitemap_entries():
            lines.append("  <url>")
            lines.append(f"    <loc>{escape(url)}</loc>")
            if lastmod:
                lines.append(f"    <lastmod>{lastmod}</lastmod>")
            for lang, href in alternates.items():
                lines.append(f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{escape(href)}"/>')
            if self.site.default_language in alternates:
                lines.append(
                    f'    <xhtml:link rel="alternate" hreflang="x-default" href="{escape(alternates[self.site.default_language])}"/>'
                )
            lines.append("  </url>")
        lines += ["</urlset>", ""]
        self.write(self.site.output_dir / "sitemap.xml", "\n".join(lines))

    def build_llms(self) -> None:
        default = self.t(self.site.default_language)["meta"]
        lines = [f"# {self.site.name}", "", f"> {default['description']}", ""]
        lines += ["## Pages", ""]
        for lang in self.site.languages:
            meta = self.t(lang)["meta"]
            lines.append(f"- [{meta['title']}]({self.site.url(lang)}): {meta['language_name']}")
        for lang in self.site.languages:
            articles = self.published(lang)
            if not articles:
                continue
            strings = self.t(lang)
            lines += ["", f"## {strings['articles']['section_title']} ({strings['meta']['language_name']})", ""]
            for article in reversed(articles):
                lines.append(f"- [{article.title}]({self.site.url(lang, article.path)}): {article.description}")
        lines.append("")
        self.write(self.site.output_dir / "llms.txt", "\n".join(lines))
