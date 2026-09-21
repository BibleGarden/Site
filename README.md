# Bible Garden — Website

Static public websites for the Bible Garden and Lampada apps, generated from
Markdown and YAML by a small Python script. The generated HTML is committed:
production nginx serves a plain checkout of `main`, nothing is built on the
server.

Domains:

- [bible.garden](https://bible.garden) — Bible Garden, repository root
- [lampada.app](https://lampada.app) — Lampada, `lampada/`

## Layout

| Path | Role |
|---|---|
| `content/<site>/site.yaml` | site name, base URL, output directory, languages, app links |
| `content/<site>/i18n/<lang>.yaml` | every visible string of the landing page, article chrome and 404 page |
| `content/<site>/articles/<slug>/<lang>.md` | article sources |
| `templates/<site>/` | Jinja2 templates: `landing.html`, `base.html`, `article.html`, `articles.html`, `404.html` |
| `templates/_shared/` | head metadata (canonical, hreflang, Open Graph) and the `?lang=` redirect |
| `sitegen/` | the generator (`python -m sitegen`) |
| `css/`, `js/`, `img/` | bible.garden static assets |
| `lampada/assets/` | lampada.app static assets |
| `privacy.html`, `lampada/privacy/`, `lampada/support/` | hand-written pages, not generated |

Generated output (do not edit by hand): `index.html`, `ru/`, `uk/`,
`articles/`, `404.html`, `robots.txt`, `sitemap.xml`, `llms.txt` at the
repository root and the same set under `lampada/`. The generator deletes and
recreates `articles/`, `ru/` and `uk/` of each site on every build, so a
removed article disappears from the output.

## Build

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m sitegen build   # rebuild both sites
.venv/bin/python -m sitegen check   # validate JSON-LD in the generated HTML
```

The build is deterministic: it embeds no timestamps, so running it twice
produces identical files. CI (`.github/workflows/build.yml`) rebuilds the site
on every pull request and fails when the committed HTML differs from the build
output or when a JSON-LD block does not parse. Commit the regenerated files
together with the content change.

Missing translation keys, unknown languages, missing frontmatter fields or a
malformed FAQ section stop the build with an error naming the file.

## URLs and languages

Languages are `en` (default, no prefix), `ru` and `uk`:

- landing pages: `/`, `/ru/`, `/uk/`
- article index: `/articles/`, `/ru/articles/`, `/uk/articles/`
- articles: `/articles/<slug>/`, `/ru/articles/<slug>/`, `/uk/articles/<slug>/`

Every page carries `canonical`, `hreflang` for the language versions that
exist and `x-default` pointing at English. Legacy links with `?lang=ru|uk|ua`
are redirected client-side to the language URL (`ua` is an alias of `uk`).
The language switcher is plain links, so search engines see every version.

The hand-written Lampada `privacy` and `support` pages and `privacy.html` on
bible.garden keep their JavaScript language switch; the generated pages link
to them with `?lang=<lang>` so the choice carries over.

## Adding an article

1. Create `content/<site>/articles/<slug>/` — the slug is the URL segment,
   lowercase latin letters, digits and hyphens, the same in every language.
2. Add one `<lang>.md` per language version (`en.md`, `ru.md`, `uk.md`). A
   language may be missing; `hreflang` then links only the versions that exist.
3. Run `python -m sitegen build`, review the page locally (see below), commit
   the sources and the generated files.

Frontmatter:

```yaml
---
title: How to start reading the Bible        # required
description: One or two sentences for search results and Open Graph.   # required
date: 2026-10-01                             # required, publication date
author: Maria Novikova                       # required
updated: 2026-10-15                          # optional, shown and used as dateModified
draft: true                                  # optional; see below
image: /img/articles/start.jpg               # optional, site-root path for Open Graph and JSON-LD
---
```

`draft: true` builds the page with `noindex`, keeps it out of the sitemap,
`llms.txt`, the article index and the previous/next navigation. The landing
page shows an "Articles" link only when the language has at least one
published article.

The body is Markdown (`extra` and `toc` extensions: tables, footnotes,
fenced code, heading anchors). Links inside the site are root-relative
(`/ru/articles/other-slug/`).

### FAQ block

A second-level heading with the `{#faq}` id marks the FAQ section. Every
third-level heading inside it is a question; the text up to the next heading
is its answer. The section renders as normal text and additionally produces a
`FAQPage` JSON-LD block.

```markdown
## Frequently asked questions {#faq}

### Which translation should I start with?

A modern one you find easy to read. The app offers WEB and BSB in English.

### How long does it take?

It depends on your pace; the app shows the audio length of every book.
```

Only one `{#faq}` section per article; every question needs an answer.

## Landing pages

The landing templates are the original hand-written pages with the text moved
to `content/<site>/i18n/<lang>.yaml`. To change copy, edit the YAML and
rebuild; to change markup, edit `templates/<site>/landing.html`. All three
YAML files of a site must define the same keys.

## Run locally

```bash
python3 -m http.server 8080            # http://localhost:8080 — bible.garden
cd lampada && python3 -m http.server 8081   # http://localhost:8081 — lampada.app
```

Lampada pages use root-absolute asset paths, so preview them from `lampada/`.

## Stack

- Python 3.12, Jinja2, Python-Markdown, PyYAML
- bible.garden: HTML + Tailwind CSS (CDN), Google Fonts (Lora, Inter), vanilla JavaScript
- lampada.app: HTML + `assets/styles.css`, system fonts, no third-party requests

The Lampada logo assets are optimized derivatives of `assets/icon.png` from
`BibleGarden/Lampada-Mobile`. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
for attribution and license.

## License

GPL v3 — see [LICENSE](LICENSE).
