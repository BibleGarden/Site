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
caption is the image alt text. Each catalog entry requires `kind` and localized
`captions`, and accepts an optional `app`: `bible-garden` (the default, no label)
or `lampada`. Unknown app values stop the build. For example:

```yaml
lampada-journal:
  kind: app
  app: lampada
  captions:
    en: Lampada journal
    ru: Дневник Lampada
    uk: Щоденник Lampada
```

Lampada screens show its icon and localized “Lampada — our second app” text
above the phone, both beside the article and below mobile section headings.
The desktop label switches with the decoded image; reserved space prevents
layout shifts. The label supports light/dark themes and remains readable text,
including without JavaScript for the first desktop screen. Its icon is copied
from `static/lampada/assets/lampada-icon-64.png` to
`static/bible-garden/img/lampada-icon-64.png` for the separate site build.

The build stops for an unknown id, malformed or
misplaced marker, missing caption, missing WebP variant, or checksum mismatch. On wide screens a
phone starts beside the breadcrumbs and header, already at its sticky top
position. The header wraps within the text column; the phone changes at marked
headings. With at least two
distinct screens, arrows and one dot per screen appear under the phone, in order
of first use in the article. The compact row never wraps: up to 12 screens use
small filled dots; longer articles show an “N / M” counter instead. These
keyboard-accessible buttons switch only the image (including its alt text and Lampada label), without scrolling the article.
The selected dot has `aria-current`; previous/next buttons stop at the ends.
A manual choice holds until another marked section crosses the reading line,
then automatic switching resumes. The pager supports light/dark themes, reserves
its space to avoid layout shifts, and stays hidden without JavaScript. Below 1024 px,
each screenshot appears below its heading and opens a larger image. Without
JavaScript the first desktop screenshot remains visible and mobile images open
as ordinary links. Sections without a marker keep the previous screen; a very
short final section may not reach the activation line on a tall screen.

The pinned screenshot archive is `bible-garden-screens-v8.zip`, prepared on
2026-10-05 (SHA-256 `eabbb4eb5b3bd65fb1c0bba9adc5a9cfab894f39cf3ca8e353b098cf2a322154`).
It preserves all 96 accepted v7 PNGs byte for byte and adds six Lampada frames:
`lampada-journal` (08-history) and `lampada-question` (03-question), each in en/ru/uk.
Sources are `store/screenshots/iphone-6.9-{en,ru,uk}-{08-history,03-question}.png`
in [Lampada-Mobile](https://github.com/BibleGarden/Lampada-Mobile/tree/2dc8d1e5c6d193bdb585f902506d409e73ccaccb/store/screenshots),
commit `2dc8d1e5c6d193bdb585f902506d409e73ccaccb`; their Git blob SHA-1 matches the GitHub Contents API
inventory verified on 2026-10-05. Lampada is not yet in the App Store as of that
date; captions describe its interface without claiming availability. Article
integration is a separate change. Accepted v7 study and large-text frames came
from [ClickUp task 123pfqn1vcr](https://app.clickup.com/t/123pfqn1vcr),
iOS-App main `4b26638`, version 1.7.
Import it with the development machine's `cwebp 1.3.2`:

```bash
.venv/bin/python tools/import_article_screens.py --site-config content/bible-garden/site.yaml /path/to/bible-garden-screens-v8.zip
.venv/bin/python -m sitegen build
.venv/bin/python -m sitegen check
```

The importer verifies the archive, its 102 named PNGs and source dimensions,
then writes WebP to `static/bible-garden/img/article-screens/{mobile,phone,zoom}/` at widths
360, 480 and 960 px with `cwebp -q 88`, plus their SHA-256 list in
`content/bible-garden/screens.sha256`. Source PNGs stay outside the repo.
The 306 WebP occupy 14.39 MiB (15,090,286 bytes). The ZIP is
64,164,280 bytes and contains 102 PNGs totalling 69,161,405 bytes. Measured on
2026-10-05 with Python `Path.stat().st_size` and `ZipFile` entry sizes; WebP
files were counted and summed in `static/bible-garden/img/article-screens/`
after import. The expected PNG list is derived from `screens.yaml`.
CI checks committed variants without needing the archive
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

Previously added article IDs are `translation-picker-english`, `reader-picker-english`,
`classic-reading-english`, `multi-step-speed`, `multi-step-translation-english`,
`multi-setup-russian-english`, and `select-psalm`. Each has all three interface
languages. New markers are integrated into articles 6.3, 6.11, 6.13 and 6.15
in en/ru/uk (checked against their source and generated pages on 2026-10-04).
The Ukrainian bilingual article retains its Ukrainian + English setup image;
the new Russian + English setup image is used in the Russian and English versions.
Use the existing `progress` screen for shared Classic / Multi Reading progress.
The full inventory, intended article sections and capture details are in the
archive's `manifest.md`; identical states under different IDs are listed in
`validation.json` and are intentional.

Ukrainian-text IDs are `translation-picker-ukrainian`, `classic-reading-ukrainian`,
`multi-reading-russian-ukrainian`, and `multi-reading-english-ukrainian`.
All four have en/ru/uk captions and interface variants. Article 6.21
(`bible-in-ukrainian`) uses Ukrainian translation selection and Khomenko reading
in all three languages, Synodal + Khomenko in ru/uk, and BSB + Khomenko in en.
Old markers showing other translations in NPU sections were removed; no NPU
capture is claimed. Checked on 2026-10-05 against the article source and
its generated HTML.

Study and large-text IDs (article drafts 6.26–6.28):

| Article | Screen ID | Placement |
| --- | --- | --- |
| 6.27, study methods | `psalm-one` | Psalm 1 example and parallel passages |
| 6.28, reading difficulties | `classic-reading-large-text` | Large Bible text (app size setting 300%) |
| 6.28, reading difficulties | `multi-step-speed-russian` | Russian Synodal / Prudovsky step, speed 0.8× |
| 6.26, Russian Synodal audio | `classic-reading-synodal` | Listening to the Synodal translation |
| 6.26, Russian Synodal audio | `multi-reading-synodal` | Synodal + Kulakov in Multi Reading |

`psalm-one.ru` has the native Synodal footnote open (Psalm 91:13; Jeremiah
17:8). Psalm 1 has no note entries in BSB or Khomenko in the production API;
the en/uk variants keep those requested translations without inventing notes.
The English BSB image also shows the native title references below its heading.
This departure from the requested open-note state needs acceptance. Captions
only describe visible content; API evidence is in the archive's `validation.json`.

No VoiceOver image or compatibility claim is included. It depends on the
separate [audit](https://app.clickup.com/t/123pfqn1vbu), which had no report on
2026-10-05. Article drafts 6.26–6.28 are not yet in Site main. The Russian 6.26 draft
is available in [PR #56](https://github.com/BibleGarden/Site/pull/56); its two
new reading markers are prepared in the task attachment
`article-6-26-screen-markers.patch` for that branch. Apply them after this
screenshot catalog change is merged. Public branches for 6.27–6.28 were still
absent when checked on 2026-10-05; use the table above when they are available.
This change does not claim article integration or the task's full acceptance.

`select-chapter` remains the v4 capture. Recapture it after the Malachi filter
fix in [ClickUp 123pfqn1u64](https://app.clickup.com/t/123pfqn1u64); v8 does not
claim that fix or an updated chapter-selection screen.

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

### Bible chapter checklist in articles

Put `<!-- checklist: bible-chapters -->` on its own line in a bible.garden
article. The author chooses its position; no article text is generated.
The marker must stay a top-level block of the article body: inside an HTML
wrapper such as a callout the build fails, because printing hides every other
child of the article body.
Unknown, malformed, duplicate and cross-site markers fail the build; markers
inside fenced code blocks remain examples. The static HTML has one labeled
checkbox per chapter, grouped by all 66 canonical books, and works without
JavaScript at widths down to 320 px. Marks are temporary, with no storage or
network requests; reloading starts a fresh checklist. JavaScript only reveals
the localized **Print checklist** button, which calls the browser print dialog.
Without JavaScript use the browser's Print command.

As with reading-plan calendars, printing an article containing this marker
prints only the checklist, excluding site navigation, header, footer and other
article content (including calendars if present). Two explicit sheets, split
after Psalms, print in three columns on two A4 portrait pages with 10 mm margins.
Use the default 100% scale and disable browser headers/footers.

Names and numbering reuse `tools/data/chapters.tsv`, `SOURCE_NT` and
`display_chapter` from `sitegen/reading_plan.py`: en uses BSB names and order;
ru uses Synodal names and app order (James–Jude immediately after Acts), with
150 Synodal-numbered Psalms and four Malachi chapters; uk uses Khomenko names
and three Malachi chapters. Totals are **1189 for en/ru**, **1188 for uk**.
Checked on 2026-10-04 with a read-only grouped chapter query against local
`cep_public.translation_verses` joined to `translations` (`bsb`, `syn`, `ubh`)
and the existing reading-time canonical limits. Translation additions outside
those limits (2 Chronicles 37, Psalm 151, Esther 11–12, Daniel 13–14) are excluded.
The three Playwright Chrome PDFs were verified with `pdfinfo`: two A4 pages
each. Regression tests: `python -m unittest discover -s tests -p test_bible_checklist.py`.

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

For the single chronological calendar, use
`<!-- plan: chronological-bible-reading-plan -->`. It has one 365-day calendar
and no reading-order switcher. Without JavaScript it contains all readings in
31-day blocks; JavaScript groups the days by real calendar months from the
chosen start date. Printing includes only this calendar and its checkboxes.
Its saved start date is independent of the two `bible-in-a-year` calendars.

The approved [chapter sequence](tools/data/chronological-sequence.json) compares
Blue Letter Bible, Back to the Bible and Tyndale/NLT through Bible In A Year
Online, with Robertson as a supplementary Gospel source. URLs, source hashes
and placement evidence are in the data; the [decision log](tools/data/chronological-decisions.md)
records disputed dates, editorial anthology contexts and source similarities.
Chapter numbering is English BSB, with Hebrew Psalm numbering. The existing
localized book names and ru/uk display mappings are reused.

The generator preserves the sequence exactly and groups the three translation
chapter pairs into indivisible units before partitioning by BSB/Bob Souer audio
duration. It first finds the smallest possible maximum deviation from the
365-day mean, then minimizes squared deviation with that maximum fixed; integer
tenths of seconds and stable tie-breaking make the result deterministic.
`chronological-bible-reading-plan.json` stores each day's `readings` as an
ordered list of `{book, first, last}` ranges (canonical numeric book IDs 1–66).
Only consecutive ascending chapters of one book are compressed; every book
change, backward jump and chapter gap remains a separate reading.

Regenerate only the chronological calendar without recomputing the existing
two calendars:

```bash
.venv/bin/python tools/validate_chronological_sequence.py
.venv/bin/python tools/build_reading_plan.py --chronological-only
.venv/bin/python -m unittest discover -s tests -p 'test_chronological*.py'
.venv/bin/python -m sitegen build
.venv/bin/python -m sitegen check
.venv/bin/python -m sitegen preview
```

Running `tools/build_reading_plan.py` without arguments regenerates all three
calendars. The build validates all plan files, including exact chronological
coverage/order, durations, non-empty days and indivisible chapter pairs.

### Multi Reading demos in articles

On bible.garden, place `<!-- demo: <id> -->` on its own line in an article,
where `<id>` names one of the JSON files in `content/bible-garden/demos/`.
The `multi-reading` kind renders John 1:1–5 as two lines per verse and plays
each verse in voice A, waits two seconds, plays it in voice B, then waits two
seconds before the next verse. The `voices` kind renders compact narrator rows;
each button plays one uninterrupted passage clip, preserving music and pauses
between verses. Starting another row stops the current one. Only the verse
currently being spoken is highlighted in a single compact passage paragraph
beneath that row. The paragraph stays open through music, pauses and completion,
until another row starts. Without JavaScript, every row's paragraph is visible;
printing shows every paragraph and hides the controls. Each button's visible label, which is also its accessible name, switches between
Play and Pause (no `aria-pressed`). A visually hidden polite live region announces
the verse being read, since highlighting alone is silent for screen readers.
Play/Pause resumes the current position, and playback
stops after the selected passage. The alternating demos use separate MP3s per verse and
prefetch the next clip. Neither kind seeks or needs HTTP Range support. Without
JavaScript, buttons stay hidden. The marker must match exactly; an
unknown, duplicate or malformed demo marker stops the build. At most one demo
renders per article.

The John 1:1–5 demos are:

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
- `ukrainian-bible` — a language pair ending in Ukrainian, for the
  `bible-in-ukrainian` article: ru is Synodal, Ilya Prudovsky and UBH
  (Khomenko), Ihor Kozlov; en is BSB, Bob Souer and UBH, Ihor Kozlov. It has
  no uk pair: for Ukrainian readers `translation-compare` pairs UBH and NPU.
- `narrators` — separate rows for each available narrator in the article's
  language, with a localized note about background music. Only Alexander
  Bondarenko's recording has music. The British WEBBE and Ukrainian NPU
  recordings have no credited narrator name.

Each demo's JSON holds its localized title, the localized labels, verse texts
and per-verse clip paths per narrator. `passages` declares the book number,
chapter per translation (so Greek and Hebrew psalm numbering can differ), an
ordered contiguous list of verse numbers, and the audio directory. Titles and
rows cover exactly the demo's supported languages; using a marker in an
unsupported language fails the build. `voices` also stores one continuous
`<first>-<last>.mp3` clip and one interval per verse. A narrator's localized name may be
`null` when the publisher does not credit one, in which case only the
translation name renders. The build rejects missing, changed or malformed
verse clips. John clips are shared between demos under
`static/bible-garden/audio/demo/<narrator>/<verse>.mp3`; continuous clips live
beside them as `1-5.mp3`. Other passages use their own `audio_dir` below
`audio/demo/`.

`tools/build_demo_audio.py` keeps a narrator registry (translation and
localized names) and a per-demo definition (id, required kind, pairs or rows, localized title); it
cuts one manifest per demo for the selected `--passage` (default `john1`). The committed `tools/data/john1-texts.tsv` comes
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

The psalm voice demos use all six verses of “The Lord is my shepherd”:

| Demo id / article language | Voices | Source psalm number |
| --- | --- | --- |
| `psalm23-voices-ru` | Prudovsky, Bondarenko, Semyonov-Prozorovsky | Synodal and BTI 22 (Greek) |
| `psalm23-voices-en` | Bob Souer, David (BSB), Winfred Henson (WEB), WEBBE (uncredited) | 23 (Hebrew) |
| `psalm23-voices-uk` | Ihor Kozlov (Khomenko), NPU (uncredited) | Khomenko 23 (Hebrew), NPU 22 (Greek) |

`tools/data/psalm23-texts.tsv` and `psalm23-timings.tsv` were exported on
2026-10-04 from local `cep_public.translation_verses` and `voice_alignments`,
joined to `translations` and `voices` by alias, for book 19 and the chapters
above; their `chapter` columns pin the numbering. Texts are exact exports
except BSB 23:1: its wrongly embedded section title `The Lord Is My Shepherd `
is removed for display (defect ticket `123pfqn1u6a`); the displayed verse is
`The Lord is my shepherd; I shall not want.` Other psalm superscriptions remain
as published. The continuous cut uses the aligned beginning of verse 1 minus
50 ms through the end of verse 6 plus 150 ms, preserving intervening music and
pauses. It excludes BSB's spoken section heading before verse 1. Highlighting
uses the original aligned verse intervals relative to that cut.

Prepare `<narrator>.mp3` files from the corresponding local app recordings
`bible-parser/audio/<translation>/<narrator>/mp3/19/<chapter:02>.mp3` (use the
processed Prudovsky file, as for John), then run:

```bash
python3 tools/build_demo_audio.py --passage psalm23 --source-dir /path/to/psalm-mp3s
.venv/bin/python -m sitegen build
.venv/bin/python -m sitegen check
.venv/bin/python -m sitegen preview
.venv/bin/python -m unittest discover -s tests
```

Psalm clips live in `static/bible-garden/audio/demo/psalm23/<narrator>/`;
John's paths stay unchanged. Use the marker `<!-- demo: psalm23-voices-ru -->`,
`<!-- demo: psalm23-voices-en -->` or `<!-- demo: psalm23-voices-uk -->` in the
corresponding language's article. Only the ru article is wired
here; the en/uk manifests are ready for their article writers. No-JS and print
behavior uses the same voices renderer, stylesheet and player as `narrators`.
On 2026-10-04, built `audio-bible-narrators/index.html` in en/ru/uk was compared
with the pre-change build using `cmp`: all three pages were byte-identical.

### Reading-time calculator in articles

On bible.garden, place `<!-- calculator: reading-time -->` on its own line.
Unknown, malformed, duplicate or cross-site markers stop the build. The JSON
in `content/bible-garden/calculator/reading-time.json` is strictly validated
on every Bible Garden build.

Choose the whole Bible, the Old Testament or the New Testament, and either
chapters per day (any positive integer, including 1–50) or a finish-by date.
Reading starts today. Editing either field updates the other; a deadline rounds
the daily chapter count up, and the result shows the actual completion date,
which can be earlier. Dates count every canonical chapter in scope: 1189 / 929 /
260, regardless of available audio. The default is three chapters per day and
no narrator. The primary result is one sentence with chapters per day and the
finish date.

Selecting one of nine recordings, grouped by language, adds approximate minutes
per day: recorded audio minutes divided by recorded chapters, multiplied by
chapters per day, capped at the total chapters in the selected scope. Missing books are named. Bondarenko has 62 books and NPU has
the New Testament and Psalms; neither changes the plan's chapter count or dates.
Chapter-division differences, such as UBH's three-chapter Malachi, retain the
recording's actual chapter count in the audio average.

The compact “Like in the Bible Garden app” details block appears only after
choosing a narrator. It offers playback speed, pauses after verses, paragraphs
or sections, and two-step Multi Reading with a second recording, its own speed
and a shared unit and pause duration. These settings change only the daily
minutes estimate. Multi Reading uses books recorded by both voices and divides
by their common recorded chapter count. It sums each voice's own unit spans,
an approximation to the app's first-translation boundaries. Timed pauses remain
wall-clock time, independent of playback speed.

The server-rendered reference table appears before the calculator card as a
standalone article table, using the normal article table styles. It is always
visible, with or without JavaScript: 1, 2, 3, 4, 5 and 10 chapters per day
for Bible / OT / NT.
Durations round to whole months using 365 days per year and 12 months per year,
with localized year/month forms (e.g. “3 года 3 месяца”). Without JavaScript the
interactive controls stay hidden. Printing shows the reference table and hides
the calculator card. The single marker renders both elements; the measured-audio
method caption appears once beneath the calculator card. The form
works at 320 px and announces results through a polite live region.

Rebuild deterministically from the committed chapter aggregates, without a
connection to the database or MP3s:

```bash
.venv/bin/python tools/build_reading_time.py
.venv/bin/python -m unittest discover -s tests -p 'test_reading_time.py'
.venv/bin/python -m sitegen build
.venv/bin/python -m sitegen check
.venv/bin/python -m sitegen preview
```

To replace source measurements, install ffmpeg on PATH and run:

```bash
.venv/bin/python tools/build_reading_time.py --export-local --decode --workers 6
```

The exporter reads only local `cep_public` in `cep-mysql`, using read-only SQL
transactions and credentials from `/root/cep/Bible-API/.env`. Local recordings
come from `/root/cep/bible-parser/audio`; `--audio-root` can select another local
directory. Credentials and raw verse/alignment dumps are never committed.
`tools/data/reading-time/` contains only per-voice per-chapter `voices.tsv`,
`alignment-anomalies.tsv` and their manifest. The existing `chapters.tsv`
provides localized book names, canonical chapter counts and the explicit New
Testament ID mapping. The generator reads verse, paragraph and heading structure for audio units. Non-canonical additions are
excluded; UBH's Malachi has three chapters rather than four.

Durations use complete normal decoding and ffmpeg's final `out_time_us`, never
MP3 header duration (WEBBE headers overstate length). Initial ID3 metadata and
David's internal encoder tags are removed in memory, preserving MPEG audio.
Damaged packets are skipped like in the player and counted in the anomalies
report; a non-zero ffmpeg exit or failure to produce audio stops generation. Each export checks identical
normal/strict durations on a clean John 1 sample from all nine voices.

Normal listening retains natural gaps: `decoded seconds / speed + units × pause`.
Multi Reading spans run from `max(first begin − 0.2, previous verse end, 0)` to
the unit's last verse end, clipped to decoded duration. Empty windows add zero.
The report lists duration differences over 20 seconds, empty windows and decoder
errors; packet counts exclude the removed ID3 metadata.

The voice measurements were exported on 2026-10-04: 9,782 chapters, six workers,
824.976 seconds. The report contains 27 duration mismatches, 5 empty windows and
12 files with decoder errors (41 bad packets). At 1×, speech-only verse/paragraph
pair approximation deviations are −0.256279% / −0.273845% for Prudovsky+Souer and
−0.036402% / −0.315252% for Kozlov+Souer; with 2-second pauses, paragraph
deviations are +3.868532% / +0.661991%.

Data sizes checked on 2026-10-04 with `Path.read_bytes()` and
`gzip.compress(data, compresslevel=9, mtime=0)`; gzip files are not committed:

| File | Raw bytes | Gzip bytes |
| --- | ---: | ---: |
| `alignment-anomalies.tsv` | 2,934 | 999 |
| `manifest.json` | 3,512 | 1,057 |
| `voices.tsv` | 615,723 | 203,421 |
| `reading-time.json` | 127,377 | 22,587 |


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

### Gospel and Apostle for today

A future bible.garden article can place `<!-- gospel-today -->` on its own line,
once, in its Russian or Ukrainian version. The marker is not supported in English
or on Lampada. No published or draft article currently uses it; draft-only fixtures
are under `tests/fixtures/gospel-today/` and are rendered by the integration tests.
The script is included only on pages using the marker.

The browser chooses the visitor's **local civil date**, including after midnight
and when returning to the tab. Russian uses ROC Julian fixed feasts, Julian Pascha
and the Lukan jump; Ukrainian uses OCU New Julian fixed feasts and Julian Pascha,
without the Lukan jump. Both show Gospel and Apostle text, additional readings,
Royal Hours, composite Gospels and Old Testament readings on non-Liturgy days.
Saints' readings, their transfers and Matins readings are not calculated.
Ukrainian dates without same-day confirmation of **all displayed passages** in the
captured OCU/UGCC liturgical evidence show `uncertain` and the church-check note.
An annual rule's general confirmation does not confirm future calendar dates.

The Russian links open Radio VERA's current Gospel and Apostle programmes.
Both languages link to the language campaign in the App Store and explain how to
open the book, chapter and verse manually. There are no chapter deep links.
Without JavaScript the page explains why it cannot determine today's local date
and retains the external calendar/listening and App Store links. No static date
is presented as today. A fixed-height, keyboard-focusable reading viewport reserves
space before loading, including errors; full texts scroll inside it. Printing
removes that height limit. Missing assets or dates show an explicit error, with no
substitute date, calendar or translation.

`sitegen/lectionary.py` computes the calendar offline from the sourced tables in
`tools/data/lectionary/tables.json`. `references.json` records dated normalized
comparison inputs and explicitly liturgical Ukrainian evidence (Matins excluded).
`verses.json` is a read-only local export; it retains Scripture coordinates and
joined-verse bounds. The public `content/bible-garden/lectionary/` has schedules
by language/year and one text dictionary per translation. The same passage is
stored once per translation and referenced by its stable ID from every day.
The build checks schemas, dates, references, text coverage and SHA-256 fingerprints,
then copies these assets to `dist/bible-garden/data/gospel-today/`.

Regenerate 2026–2030 deterministically from committed sources, without DB/network:

```bash
.venv/bin/python tools/build_gospel_today.py --start-year 2026 --end-year 2030
.venv/bin/python -m sitegen build
.venv/bin/python -m sitegen check
.venv/bin/python -m sitegen preview
.venv/bin/python -m unittest discover -s tests
```

To replace the Scripture snapshot, add `--export-local` to the generator command.
It queries only local `cep_public` in `cep-mysql` in a read-only SQL transaction,
using credentials from `/root/cep/Bible-API/.env` without printing them. DB book IDs
for the Epistles are explicitly converted to the canonical order. Texts are
Synodal (`syn`) and Khomenko (`ubh`); the owner authorized open UBH JSON publication
on 2026-10-05. No text is downloaded or substituted. UBH Romans 14:24–26 is
explicitly mapped to 16:25–27 and displayed with the target coordinates. The verified Khomenko Matthew 23:14–15 source range is explicitly normalized
from the local 14/text + 15/empty representation to one joined verse; unknown
empty records still fail (evidence and tests in the input README). Combined
verses and cross-chapter passages preserve their actual translation boundaries.

Extend the explicit range annually, exporting again if new passages require data;
commit sources, regenerated JSON and `dist/` together. There is no clock-dependent
build or automatic network refresh. Paschalion accepts 1900–2099; daily calculation
requires 1901–2098 because it uses adjacent Paschal years. The initial output ends
on 2030-12-31. Measured on 2026-10-05 after regeneration: 4,499,751 bytes of
public JSON, with 768 unique passages per translation; detailed counts and gzip
measurements are in the input README. Rare Annunciation/Holy Week coincidences follow the documented
feast-first model and need church verification; future Ukrainian winter repeats
are projected and marked unconfirmed until dated evidence is added.

The source comparison measures the first Gospel (first composite/Hours component,
or first Old Testament reading when no Gospel exists), not every Apostle or
secondary passage. Empty-source days remain counted separately; adjacent-day
matches describe saints' transfers and never change displayed dates. Tests pin
both the denominators and thresholds: Azbyka ROC ≥95% exact and ≥99% with adjacent
matches, pravoslavie ROC ≥93%, OCU ≥91%, UGCC ≥92% exact. Further details and dated
measurements are in `tools/data/lectionary/README.md`.
