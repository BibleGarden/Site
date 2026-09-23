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
| `content/<site>/site.yaml` | site name, base URL, output directory, languages and their switcher labels, article author, app links, analytics |
| `content/<site>/i18n/<lang>.yaml` | every visible string of the landing page, article chrome and 404 page |
| `content/<site>/articles/<slug>/<lang>.md` | article sources |
| `content/<site>/pages/<slug>/<lang>.md` | standalone pages such as `/about/` (optional directory) |
| `templates/<site>/` | Jinja2 templates: `landing.html`, `base.html`, `article.html`, `articles.html`, `404.html`, `page.html` (only for a site with pages) |
| `templates/_shared/` | head metadata (canonical, hreflang, Open Graph) and the `?lang=` redirect |
| `sitegen/` | the generator (`python -m sitegen`) |
| `css/`, `js/`, `img/` | bible.garden static assets |
| `lampada/assets/` | lampada.app static assets |
| `privacy.html`, `lampada/privacy/`, `lampada/support/` | hand-written pages, not generated |

Generated output (do not edit by hand): `index.html`, `ru/`, `uk/`,
`articles/`, one directory per page (`about/`), `404.html`, `robots.txt`, `sitemap.xml`, `llms.txt` at the
repository root and the same set under `lampada/`. The generator deletes and
recreates `articles/`, `ru/`, `uk/` and the page directories of each site on
every build, so a removed article disappears from the output (a removed page
leaves its default-language directory behind: delete it by hand); `output_dir` in `site.yaml` must
therefore be a relative path inside the repository, and those directories
must not overlap `content/`, `templates/`, `sitegen/`, `.git/` or `.github/`. Every site needs a
`content/<site>/articles/` directory, even an empty one.

## Build

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m sitegen build   # rebuild both sites
.venv/bin/python -m sitegen check   # validate JSON-LD, hreflang, internal links and analytics tags
```

The build is deterministic: it embeds no timestamps, so running it twice
produces identical files. CI (`.github/workflows/build.yml`) rebuilds the site
on every pull request and fails when the committed HTML differs from the build
output, when an indexable page lacks a single `canonical` resolving to itself,
when another language version of the page exists on disk but is not linked, when a
page's `hreflang` set is incomplete (every published version, itself and
`x-default`), differs between versions, or points at a page with another
`<html lang>`, another canonical or `noindex`,
when a JSON-LD block lacks a required field (`Article`: headline,
image, dates, an `Organization` author with name and URL; `AboutPage` and
`WebPage`: name, description, URL, language, and for `AboutPage` the
`Organization`; `BreadcrumbList`: items; `FAQPage`: questions with answers), when a `hreflang` link points at a `noindex` page or when a page's
analytics tag disagrees with `site.yaml` (see [Analytics](#analytics)). Commit the
regenerated files together with the content change.

Missing translation keys, unknown languages, missing frontmatter fields or a
malformed FAQ section stop the build with an error naming the file.

## URLs and languages

Languages are `en` (default, no prefix), `ru` and `uk`:

- landing pages: `/`, `/ru/`, `/uk/`
- article index: `/articles/`, `/ru/articles/`, `/uk/articles/`
- articles: `/articles/<slug>/`, `/ru/articles/<slug>/`, `/uk/articles/<slug>/`
- pages: `/<slug>/`, `/ru/<slug>/`, `/uk/<slug>/` (bible.garden: `/about/`)

Every indexable page carries `canonical`, `hreflang` for the published
language versions and `x-default` pointing at English (or, when there is no
English version, at the first published one); `noindex` pages
(drafts, an empty article index, `404.html`) carry no `hreflang` and are never
linked as alternates. The language switcher is plain links, so search engines
see every version.

`/` stays the English page rather than a redirector to `/en/`: it is the URL
the App Store and existing search results point at, and crawlers without
JavaScript must see content there. A small inline script on every generated
page handles the language choice client-side:

- `?lang=ru|uk|ua` on a landing page (the only pages such legacy links
  point at) redirects to the language URL (`ua` is an
  alias of `uk`) and records the choice;
- on the English landing page only, a language recorded earlier wins;
  otherwise a browser whose `navigator.languages` prefers `ru` or `uk` is sent
  to `/ru/` or `/uk/`. English-first browsers (and crawlers) stay on `/`;
- on article and article-index pages the switcher always lists every site
  language: an existing version is a link (for a draft, other drafts count),
  a missing one is a greyed-out, non-clickable label whose tooltip lists the
  available languages; `hreflang` still lists only published versions;
- clicking the language switcher records the choice in `localStorage`
  (`storage_key` in `site.yaml`), so a visitor who picked English on `/ru/`
  is not redirected from `/` again.

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
updated: 2026-10-15                          # optional, shown and used as dateModified
draft: true                                  # optional; see below
image: /img/articles/start.jpg               # optional, site-root path for Open Graph and JSON-LD
---
```

There is no `author` key: every article is signed by the site's author (see
[Author](#author)); an `author` key stops the build as unknown.

Without `image` the site logo (1024×1024) is used. Real articles should set
`image` to a picture at least 1200 px wide (16:9, 4:3 or 1:1), which is what
Google expects for `Article` rich results.

`draft: true` builds the page with `noindex`, keeps it out of the sitemap,
`llms.txt`, the article index and the previous/next navigation. The landing
page shows an "Articles" link only when the language has at least one
published article.

Links between pages of the same site are root-relative (`/ru/articles/slug/`)
so a local preview never jumps to production; absolute URLs appear only in
`canonical`, `hreflang`, Open Graph, the sitemap, `llms.txt`, JSON-LD and
links to the other site. `sitegen check` rejects an `<a href>` to the page's
own domain.

The body is Markdown (`extra` and `toc` extensions: tables, footnotes,
fenced code, heading anchors). Headings inside fenced code blocks (``` or ~~~,
CommonMark rules) are ignored by the FAQ parser. Links inside the site are root-relative
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

## Author

Articles are signed by an organization, not a person. `site.yaml` defines it:

```yaml
author:
  name: {en: Bible Garden team, ru: Команда Bible Garden, uk: Команда Bible Garden}
  page: about/     # '' links to the landing page
```

`name` needs every site language. The byline under the article title links to
`page` in the article's language, and the `Article` JSON-LD carries
`"author": {"@type": "Organization", "name": …, "url": …}` with the same URL.
A non-empty `page` must be a page from `content/<site>/pages/` published in
every language, otherwise the build stops. bible.garden links to "How we
write" (`/about/`); lampada.app has no such page yet and links to its landing
page.

## Pages

`content/<site>/pages/<slug>/<lang>.md` builds `/<slug>/`, `/ru/<slug>/`,
`/uk/<slug>/` with the site's `page.html`. Frontmatter holds exactly `title`
and `description`; the body is Markdown as in articles. Pages get canonical,
`hreflang`, the language switcher, a sitemap entry and a line in `llms.txt`.
The author's page carries `AboutPage` JSON-LD with the author `Organization`
as `mainEntity`; any other page carries `WebPage`. A slug must not be
`articles` or a language code, and the build refuses a page whose
default-language directory already holds anything but `index.html`, so a page
cannot overwrite `img/` or a hand-written page.

## App Store links

The landing pages keep `app_store_url`. Every other generated page of
bible.garden (articles, the article index, pages, 404) links to the App Store
campaign of its language:

```yaml
article_app_store_url: https://apps.apple.com/app/apple-store/id6758955373?pt=119043617&ct=seo-{lang}&mt=8
```

`{lang}` becomes `en`, `ru` or `uk`, so App Store Connect analytics
reports installs by campaign: `seo-en`, `seo-ru`, `seo-uk`;
`pt=119043617` is the provider token of our account. Apple does not tell
articles of one language apart; clicks per article are the Umami event
`app-store-click` (see [Analytics](#analytics)).

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

## Analytics

Visits can be counted with Umami running on our production server at
`stats.bible.garden` (deployment: `Deploy/runbook.md`, "Umami"). Both sites
have `analytics: none` until that rollout. Every
`site.yaml` must set `analytics` explicitly; a missing key, an empty value or a
malformed one stops the build:

```yaml
analytics: none            # no tracker on any page of this site

analytics:                 # tracker on every page of this site
  script_url: https://stats.bible.garden/script.js
  website_id: 00000000-0000-0000-0000-000000000000   # Umami: Settings → Websites → the site
```

With a mapping, every generated page gets one
`<script defer src="…" data-website-id="…" data-domains="<site host>"
data-exclude-search="true" data-exclude-hash="true">` before `</head>`.
`data-domains` is the host of `base_url`, so local previews send nothing; the
two `exclude` flags make the tracker drop query strings and fragments from the
page and referrer URLs, so Umami never stores them. Links to the App Store carry `data-umami-event="app-store-click"`
regardless of the setting; the attribute is inert without the tracker.

`sitegen check` requires, on every HTML page of a site, hand-written pages
included, exactly that tag when analytics is on and no tracker when it is
`none` (a `<script>` with `data-website-id`, a `/script.js` or `umami` source,
or a source on another site's tracker host), and the event attribute on every App Store link.

Turning analytics on for a site:

The switch-on happens in one pull request from the branch
`feat/123pfqn03e5-umami-enable`, which already holds the privacy policy texts
describing Umami (proofread before use):

1. Create the website in Umami and copy its website ID.
2. Replace `analytics: none` in `content/<site>/site.yaml` with the mapping above.
3. `python -m sitegen build`.
4. Paste the same tag by hand before `</head>` of the site's hand-written pages
   (`privacy.html` for bible.garden; `lampada/privacy/index.html` and
   `lampada/support/index.html` for lampada.app). `sitegen check` prints the
   exact tag if a page lacks it.
5. `python -m sitegen check`, commit together with the privacy texts, deploy.

## Stack

- Python 3.12, Jinja2, Python-Markdown, PyYAML
- bible.garden: HTML + Tailwind CSS (CDN), Google Fonts (Lora, Inter), vanilla JavaScript
- lampada.app: HTML + `assets/styles.css`, system fonts, no third-party requests
- analytics, once switched on: self-hosted [Umami](https://umami.is) at
  `stats.bible.garden` on our own server (first party, no cookies); see
  [Analytics](#analytics)

The Lampada logo assets are optimized derivatives of `assets/icon.png` from
`BibleGarden/Lampada-Mobile`. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
for attribution and license.

## License

GPL v3 — see [LICENSE](LICENSE).
