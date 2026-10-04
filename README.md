# Bible Garden — Website

Static public websites for the Bible Garden and Lampada apps, generated from
Markdown and YAML by a small Python script. The complete public output is
committed under `dist/`; production serves those directories after the Deploy
root switch. This cleanup removes the former root-level public tree only after
that switch has been verified on production.

Domains:

- [bible.garden](https://bible.garden) — `dist/bible-garden/`
- [lampada.app](https://lampada.app) — `dist/lampada/`

## Layout

| Path | Role |
|---|---|
| `content/<site>/site.yaml` | site name, base URL, languages and their switcher labels, article author, app links, analytics |
| `content/<site>/i18n/<lang>.yaml` | every visible string of the landing page, article chrome and 404 page |
| `content/<site>/articles/<slug>/<lang>.md` | article sources |
| `content/<site>/pages/<slug>/<lang>.md` | standalone pages such as `/about/` (optional directory) |
| `templates/<site>/` | Jinja2 templates: `landing.html`, `base.html`, `article.html`, `articles.html`, `404.html`, `page.html` (only for a site with pages) |
| `templates/_shared/` | head metadata (canonical, hreflang, Open Graph) and the `?lang=` redirect |
| `sitegen/` | the generator (`python -m sitegen`) |
| `static/bible-garden/css/`, `js/`, `img/` | bible.garden static sources |
| `static/lampada/assets/` | lampada.app static sources |
| `static/bible-garden/privacy.html`, `static/lampada/privacy/`, `support/` | hand-written page sources |
| `dist/<site>/` | committed public HTML and copied static files; nginx roots |
| `.preview/<site>/` | ignored local preview, including draft articles |

The build recreates `dist/` from scratch. Each site contains generated
`index.html`, language and article directories, page directories, `404.html`,
`robots.txt`, `sitemap.xml`, `llms.txt`, plus only its explicit static inputs.
Bible Garden copies its `css/`, `js/`, `img/`, `privacy.html` static sources;
Lampada copies `assets/`, `privacy/`, `support/`. Draft HTML is absent
from `dist/`. The output path is derived as `dist/<site>/` from the content
directory name. Every site needs a
`content/<site>/articles/` directory, even an empty one.

## Build

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m sitegen build   # rebuild both sites
.venv/bin/python -m sitegen check   # compare dist byte for byte and validate references/metadata
.venv/bin/python -m sitegen preview # optional: build local draft previews into .preview/
.venv/bin/python -m unittest discover -s tests
```

The build is deterministic: it embeds no timestamps, so running it twice
produces identical files. CI (`.github/workflows/build.yml`) rebuilds the site
on every pull request and fails when the committed `dist/` differs from the build
output.
It also fails when an indexable page lacks a single `canonical` resolving to itself,
when another language version of the page exists on disk but is not linked, when a
page's `hreflang` set is incomplete (every published version, itself and
`x-default`), differs between versions, or points at a page with another
`<html lang>`, another canonical or `noindex`,
when a JSON-LD block lacks a required field (`Article`: headline,
image, dates, an `Organization` author with name and URL; `AboutPage` and
`WebPage`: name, description, URL, language, and for `AboutPage` the
`Organization`; `BreadcrumbList`: items; `FAQPage`: questions with answers), when a `hreflang` link points at a `noindex` page or when a page's
analytics tag disagrees with `site.yaml` (see [Analytics](#analytics)), or when a
committed article screenshot is missing, corrupt or has the wrong dimensions. Commit the
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

`draft: true` builds the page with `noindex` only in `.preview/`; new public
`dist/` contains no draft page. Draft URLs return 404 on production.
Drafts stay out of the sitemap, `llms.txt`, the article
index and the previous/next navigation. The landing page shows up to three
latest published articles in its own language, followed by an article-index
link; the block and menu link are absent when that language has no published
articles. The footer link is unconditional on every bible.garden page, including
the hand-written privacy page and languages with no published articles.

Links between pages of the same site are root-relative (`/ru/articles/slug/`)
so a local preview never jumps to production; absolute URLs appear only in
`canonical`, `hreflang`, Open Graph, the sitemap, `llms.txt`, JSON-LD and
links to the other site. `sitegen check` rejects an `<a href>` to the page's
own domain.

The body is Markdown (`extra` and `toc` extensions: tables, footnotes,
fenced code, heading anchors). Headings inside fenced code blocks (``` or ~~~,
CommonMark rules) are ignored by the FAQ parser. Links inside the site are root-relative
(`/ru/articles/other-slug/`).

### Screens in articles

Add a marker on the line immediately after a second-level heading:

```markdown
## Which translation should I choose?
<!-- screen: translation-picker -->
```

Any HTML comment directly under an `h2` must use this exact syntax; a
screen-like comment elsewhere in article text also stops the build.

The id must exist in `content/bible-garden/screens.yaml`; the article language
selects its caption and image (`translation-picker.ru.webp` for `ru.md`). The
caption is the image alt text. The build stops for an unknown id, malformed or
misplaced marker, missing caption, missing WebP variant, or checksum mismatch. On wide screens a
phone stays beside the article and changes at marked headings; below 1024 px,
each screenshot appears below its heading and opens a larger image. Without
JavaScript the first desktop screenshot remains visible and mobile images open
as ordinary links. Sections without a marker keep the previous screen; a very
short final section may not reach the activation line on a tall screen.

The accepted screenshot archive is the latest `bible-garden-screens-v4.zip`
attachment of ClickUp task `123pfqn05hq` (SHA-256
`70a13a2da5727fe0671eb6a712a7448485f7ec9e3ede220ecc384fa547a2e9fb`).
Import it with the development machine's `cwebp 1.3.2`:

```bash
.venv/bin/python tools/import_article_screens.py --site-config content/bible-garden/site.yaml /path/to/bible-garden-screens-v4.zip
.venv/bin/python -m sitegen build
.venv/bin/python -m sitegen check
```

The importer verifies the archive, its 48 named PNGs and source dimensions,
then writes WebP to `static/bible-garden/img/article-screens/{mobile,phone,zoom}/` at widths
360, 480 and 960 px with `cwebp -q 88`, plus their SHA-256 list in
`content/bible-garden/screens.sha256`. Source PNGs stay outside the repo.
The current 144 WebP occupy 6.87 MiB (measured on 2026-09-24 by summing file
sizes after import). CI checks committed variants without needing the archive
or `cwebp`. The draft `template-check` article exercises two markers in all
three languages; its HTML exists only after `python -m sitegen preview`.
Preview `/ru/articles/template-check/` with the local server described below.

To upgrade `cwebp`, change `CWEBP_VERSION` in
`tools/import_article_screens.py`, install that exact version, rerun the
importer, and commit all regenerated WebP and `screens.sha256` together. To
accept a new archive version, update `ARCHIVE_SHA256` in the same script
(and `SOURCE_PREFIX` if the archive directory changed), review its files and
captions in `screens.yaml`, then import and commit the WebP and checksums in
the same change.

### Callout

To make a key paragraph stand out for skimming readers, wrap it in a callout
(Markdown inside is rendered thanks to `md_in_html` from `extra`):

```markdown
<div class="article-callout" markdown="1">
**Multi Reading is the app's key feature.** Every verse plays twice…
</div>
```

Use it sparingly — at most one per article.

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

### Reading plan in articles

On bible.garden, put `<!-- plan: bible-in-a-year -->` on its own line where the
calendars should appear. The build rejects unknown or malformed markers. Both
365-day plans are in the HTML: **Parallel** reads the Old Testament without
Psalms alongside the New Testament followed by Psalms; **Straight through**
reads Genesis through Revelation in canonical order. Without JavaScript both
appear, each with a heading and 31-day blocks (`Days 1–31`, `Days 32–62`, etc.).
With JavaScript a radio switcher shows one plan and remembers the choice. The
selected start date fills both calendars and groups their days by real calendar
month, including partial first and last months. Printing includes only the
selected plan and flows without a page break per month; without JavaScript,
both plans print. The readings and print checkboxes are always in the HTML.

The committed `tools/data/chapters.tsv` comes from `cep_public.voice_alignments`
(BSB, Bob Souer), exported on 2026-09-27. Its New Testament IDs 45–65 place
James–Jude before Romans–Hebrews; the generator explicitly maps them to
Protestant canonical order. It first partitions the New Testament–Psalms
stream, then exactly partitions the Old Testament stream against those day
durations. It alternates the two streams for up to eight improvements. The
sequential plan exactly partitions all 1189 chapters as one stream. Each
partition minimizes the maximum deviation of daily audio duration from the
365-day mean, then the total squared deviation. The two committed JSON files
are in `content/bible-garden/plans/`.

The JSON keeps Hebrew/BSB chapter numbers. Days never split Psalms 9–10 or
114–115, or Malachi 3–4. The ru calendar displays Greek/Septuagint Psalm
numbers used by Synodal and Kulakov/BTI; uk displays Malachi as three chapters
and keeps Hebrew Psalm numbers. These translation chapter schemes were checked
against `cep_public.translation_verses` on 2026-09-27.
The TSV corrects the export's Russian book 22 name to «Песнь песней».

Regenerate and rebuild with:

```bash
.venv/bin/python tools/build_reading_plan.py
.venv/bin/python -m sitegen build
```

### Multi Reading demos in articles

On bible.garden, place `<!-- demo: <id> -->` on its own line in an article,
where `<id>` names one of the JSON files in `content/bible-garden/demos/`.
The `multi-reading` kind renders John 1:1–5 as two lines per verse and plays
each verse in voice A, waits two seconds, plays it in voice B, then waits two
seconds before the next verse. The `voices` kind renders compact narrator rows;
each button plays one uninterrupted John 1:1–5 clip, preserving music and pauses
between verses. Starting another row stops the current one. Only the verse
currently being spoken is highlighted in a single compact John 1:1–5 paragraph
beneath that row. The paragraph stays open through music, pauses and completion,
until another row starts. Without JavaScript, every row's paragraph is visible;
printing shows every paragraph and hides the controls. Each button's visible label, which is also its accessible name, switches between
Play and Pause (no `aria-pressed`). A visually hidden polite live region announces
the verse being read, since highlighting alone is silent for screen readers.
Play/Pause resumes the current position, and playback
stops after verse 5. The alternating demos use separate MP3s per verse and
prefetch the next clip. Neither kind seeks or needs HTTP Range support. Without
JavaScript, buttons stay hidden. The marker must match exactly; an
unknown, duplicate or malformed demo marker stops the build. At most one demo
renders per article.

Three demos exist:

- `multi-reading` — the same passage in two languages. The ru pair is BTI
  (Kulakov), Nikita Semyonov-Prozorovsky and BSB, Bob Souer; en is BSB, Bob
  Souer and Synodal, Ilya Prudovsky; uk is UBH (Khomenko), Ihor Kozlov and
  BSB, Bob Souer.
- `translation-compare` — two translations of the same language, so readers
  hear how translators differ. The ru pair is Synodal, Alexander Bondarenko and BTI
  (Kulakov), Nikita Semyonov-Prozorovsky; en is BSB, Bob Souer and World
  English Bible, Winfred Henson; uk is UBH (Khomenko), Ihor Kozlov and the New
  Ukrainian Translation (NPU) — Biblica does not credit a narrator for NPU, so
  its clips carry no narrator name.
- `narrators` — separate rows for each available narrator in the article's
  language, with a localized note about background music. Only Alexander
  Bondarenko's recording has music. The British WEBBE and Ukrainian NPU
  recordings have no credited narrator name.

Each demo's JSON holds its localized title, the localized labels, verse texts
and the five per-verse clip paths per narrator. `voices` also stores one
`1-5.mp3` clip and five verse intervals per narrator. A narrator's localized name may be
`null` when the publisher does not credit one, in which case only the
translation name renders. The build rejects missing, changed or malformed
verse clips. Clips are shared between demos under
`static/bible-garden/audio/demo/<narrator>/<verse>.mp3`; continuous clips live
beside them at `static/bible-garden/audio/demo/<narrator>/1-5.mp3`.

`tools/build_demo_audio.py` keeps a narrator registry (translation and
localized names) and a per-demo definition (id, required kind, pairs or rows, localized title); it
cuts one manifest per demo. The committed `tools/data/john1-texts.tsv` comes
from `cep_public.translation_verses` (WEBBE exported 2026-09-28); `tools/data/john1-timings.tsv` comes
from `cep_public.voice_alignments` (John 1; bsb/bti/syn/ubh and their
narrators exported 2026-09-27, webus/npu, their narrators and the Synodal narrator
`bondarenko`, plus `bsb_david` and `web_british` exported 2026-09-28). The full-chapter recordings are not committed. Cut clips from the files served by the app,
`bible-parser/audio/<translation>/<voice>/mp3/43/01.mp3`. Public URL provenance
comes from `cep_public.voices.link_template`: `prozorovsky.mp3` and `bondarenko.mp3` from 4bbl.ru,
`bsb_souer.mp3` from openbible.com, `prudovsky.mp3` from mp3.only.bible,
`kozlov_uk.mp3` from wordproaudio.net and `winfred_henson.mp3` from
publicdomainaudiobibles.com (`https://www.publicdomainaudiobibles.com/content/
mp3/WEBW/...`); `bsb_david.mp3` is from `bible-parser/audio/bsb/bsb_david/mp3/43/01.mp3`
(`https://openbible.com/audio/david/BSB_{book_code5}_{chapter_zerofill3}_D.mp3`);
`web_british.mp3` is from `bible-parser/audio/webbe/web_british/mp3/43/01.mp3`
(`https://ebible.org/eng-webbe/mp3/...`); `npu_uk.mp3` has no public URL
(Biblica does not publish one). The public mp3.only.bible Prudovsky file is the
unprocessed original: the app serves `bible-parser/audio/syn/prudovsky/mp3/43/01.mp3`
with the sibilant whistle removed. Use that improved local file for demo cuts;
the verse timings were aligned on it.

Put any subset of `<narrator>.mp3` files (named after the registry keys in
`tools/build_demo_audio.py`) in one or more local directories and regenerate
the mono, 56 kbps verse and continuous clips and every demo's manifest with:

```bash
python3 tools/build_demo_audio.py --source-dir /path/to/john1-mp3s
.venv/bin/python -m sitegen build
```

`--source-dir` may be repeated; every given directory must exist and together
they must hold at least one source, otherwise the tool stops. Only narrators whose `<narrator>.mp3` is found
in one of the given directories are (re-)cut — ffmpeg is deterministic, so
re-cutting an existing narrator from the same source reproduces byte-identical
clips, and narrators already cut in an earlier run do not need their source
file again. Adding a new demo or narrator therefore only needs the new
narrators' source files, not the older ones. Reused clips must match their
existing manifest checksums and durations, and their timing fingerprint must
match the committed timeline; changing a narrator's timings requires its
source MP3.

### Reading-time calculator in articles

On bible.garden, place `<!-- calculator: reading-time -->` on its own line.
Unknown, malformed, duplicate or cross-site markers stop the build. The JSON
in `content/bible-garden/calculator/reading-time.json` is validated during every
Bible Garden build, including when no published article uses the marker.

The block estimates listening or silent reading for the whole Bible, either
Testament, the Gospels, Psalms, or one of 66 books. Defaults follow the page
language: Prudovsky / Bob Souer / Kozlov, and 190 / 238 / 190 words per minute.
The silent-reading defaults follow Brysbaert (2019), with Russian/Ukrainian
scaled by word count; the Ukrainian value is an estimate, not a measured norm.
Users can edit their pace, playback speed, timed pauses, and daily minutes or
an inclusive finish date. Two-step Multi Reading has separate speeds and
pauses. Only books available in both selected recordings are included; missing
books are named and never extrapolated.

Without JavaScript, a server-rendered table lists the page language's recordings
at 1× and translations at the default silent-reading pace for Bible / OT / NT.
Printing shows that table and the method caption, with controls and interactive
results hidden. The form is usable at 320 px and announces results politely.

Regenerate from the committed chapter aggregates, without a database or MP3s:

```bash
.venv/bin/python tools/build_reading_time.py
.venv/bin/python -m sitegen build
.venv/bin/python -m sitegen check
.venv/bin/python -m unittest discover -s tests -p 'test_reading_time.py'
```

To replace the source measurements, install `ffmpeg` on PATH, keep the original
app recordings under `/root/cep/bible-parser/audio`, and run:

```bash
.venv/bin/python tools/build_reading_time.py --export-local --decode --workers 6
```

`--audio-root /path/to/local/audio` can select another local recording directory.
The exporter connects only to the local `cep-mysql` container's `cep_public`,
using read-only SQL transactions. It reads `DB_PASSWORD` from the local
`/root/cep/Bible-API/.env`; credentials are never stored in this repository.
It exports only chapter aggregates (`voices.tsv`, `translations.tsv`), an
`alignment-anomalies.tsv` report and a manifest under `tools/data/reading-time/`.
The manifest fingerprints the sources and checksums every TSV. Raw verses and
alignments stay in memory and are not committed. The existing `chapters.tsv`
provides localized book names and the explicit New Testament order mapping.
Canonical additions (Daniel 13–14, Psalm 151, Esther 11–12, etc.) are excluded;
UBH's three-chapter Malachi is a numbering difference, not missing coverage.

Recording lengths come from complete normal decoding, using final ffmpeg
`out_time_us`, never MP3 header duration (WEBBE headers overstate length).
Initial ID3 metadata and David's exact internal `Lavf59.27.100` encoder tags are
removed in memory before decoding; MPEG audio is unchanged. Normal decoding
skips damaged packets, matching playable audio. Every file with decoder errors
is listed with its bad-packet count; a hard failure producing no audio stops
generation. Each export compares normal and strict durations on nine clean
John 1 files (one per voice); they must be identical.

Normal listening is `decoded seconds / speed + unit count × pause seconds`;
it retains natural gaps. Multi Reading sums each unit from
`max(first begin − 0.2, previous verse end, 0)` to its last verse end,
intersected with the decoded file's duration (empty windows contribute zero),
then divides by that step's speed
and adds wall-clock pauses. Units follow paragraph starts and all preceding
titles, including the first block of every chapter; joined verses follow the
app's `(number + join, number)` order. Every chapter differing from alignment
end by more than 20 seconds appears in the anomaly report, alongside decoder
errors and overlapping units with empty windows. These are separate report
rows (`duration_mismatch`, `decoder_errors`, `empty_window`); packet counts
exclude the ID3 metadata removed before decoding.

Multi Reading uses each voice's own units, approximating the app's first-
translation boundaries; the exporter measures deviation at 1×,
both without pauses and with 2 seconds after each step, for Prudovsky+Souer and Kozlov+Souer (verse/paragraph).
It also reports UBH/Souer's Malachi chapter-count difference in that comparison.
Measured on 2026-10-04 by the full export command above: 9,782 chapters,
six workers, **824.976 seconds**. Rebuilding JSON from the committed TSVs
took **0.079 seconds**, without database access or decoding. The clean sample's
nine normal/strict durations matched exactly. The report contains **27 duration
mismatches, 5 empty windows and 12 files with decoder errors (41 bad packets)**.
The empty windows include Bondarenko Exodus 1:21 / 18:14, Henson Genesis 15:15,
and Semyonov-Prozorovsky Exodus 16:34 / Job 24:3 after joined-verse ordering.

At 1×, speech-only verse/paragraph deviations against exact app pair indexing
are **−0.256279% / −0.273845%** for Prudovsky+Souer and
**−0.036402% / −0.315252%** for Kozlov+Souer; with 2-second pauses after each
step, paragraph deviations are **+3.868532% / +0.661991%**, respectively.

Data sizes measured on 2026-10-04 with `Path.read_bytes()` and
`gzip.compress(data, compresslevel=9, mtime=0)`; gzip files are not committed:

| File | Raw bytes | Gzip bytes |
| --- | ---: | ---: |
| `alignment-anomalies.tsv` | 2,934 | 999 |
| `manifest.json` | 3,604 | 1,104 |
| `translations.tsv` | 176,408 | 48,007 |
| `voices.tsv` | 615,723 | 203,421 |
| `reading-time.json` | 185,557 | 27,412 |


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

On bible.garden the footer of every page links to "How we write" next to the
privacy policy (string `landing.footer.about`); the hand-written
`privacy.html` carries the same link and sets its language URL in `setLang`.

## Pages

`content/<site>/pages/<slug>/<lang>.md` builds `/<slug>/`, `/ru/<slug>/`,
`/uk/<slug>/` with the site's `page.html`. Frontmatter holds exactly `title`
and `description`; the body is Markdown as in articles. Pages get canonical,
`hreflang`, the language switcher, a sitemap entry and a line in `llms.txt`.
The author's page carries `AboutPage` JSON-LD with the author `Organization`
as `mainEntity`; any other page carries `WebPage`. A slug must not be
`articles` or a language code, and the build stops when a page's slug matches
a static directory (`img/` or `privacy/`), so a page
cannot overwrite a hand-written one.

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
cd dist/bible-garden && python3 -m http.server 8080
cd dist/lampada && python3 -m http.server 8081
```

Run those commands in separate shells. To view drafts, first run
`.venv/bin/python -m sitegen preview`, then serve `.preview/bible-garden/` and
`.preview/lampada/` in the same way. Each site must have its own document root
because its asset URLs are root absolute.

## Production deployment

Deploy Site with `git pull --ff-only origin main` in `/root/cep/site`; nginx
serves the pulled files without a restart. The full procedure is in the Deploy
runbook, section "Site".

## Analytics

Visits are counted with Umami running on our production server at
`stats.bible.garden` (deployment: `Deploy/runbook.md`, "Umami"). Both sites
configure their own website ID. Every
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
page and referrer URLs, so Umami never stores them. Links to the site's own app in the App Store (the id from `app_store_url`) carry
`data-umami-event="app-store-click"` regardless of the setting; the attribute is inert without the tracker.
Links to other apps (for example in app comparisons) are not tracked.

`sitegen check` requires, on every HTML page of a site, hand-written pages
included, exactly that tag when analytics is on and no tracker when it is
`none` (a `<script>` with `data-website-id`, a `/script.js` or `umami` source,
or a source on another site's tracker host), and the event attribute on every App Store link.

When changing a site's analytics settings, run `python -m sitegen build` and
paste the resulting tag by hand before `</head>` of its hand-written pages
(`static/bible-garden/privacy.html` for bible.garden;
`static/lampada/privacy/index.html` and
`static/lampada/support/index.html` for lampada.app). `sitegen check` prints the exact
tag if a page lacks it. Commit generated and hand-written pages together with
the configuration change.

## Stack

- Python 3.12, Jinja2, Python-Markdown, PyYAML
- bible.garden: HTML + Tailwind CSS (CDN), Google Fonts (Lora, Inter), vanilla JavaScript
- lampada.app: HTML + `assets/styles.css`, system fonts, no third-party requests
- analytics: self-hosted [Umami](https://umami.is) at
  `stats.bible.garden` on our own server (first party, no cookies); see
  [Analytics](#analytics)

The Lampada logo assets are optimized derivatives of `assets/icon.png` from
`BibleGarden/Lampada-Mobile`. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
for attribution and license.

## License

GPL v3 — see [LICENSE](LICENSE).
