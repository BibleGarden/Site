# Lampada article evidence

Articles remain `content/lampada/articles/<slug>/<lang>.md`. Add optional
`corpus_sources` to their YAML front matter. Each entry binds one literal span
of article Markdown to one corpus chunk; put `[^corpus-<id>]` immediately after
that span in the body. The build validates the schema and generates a Markdown
footnote containing author, work, chapter, translator (when non-null) and a link
to the original source, naming its host (including Predanie.ru).
It never requests the corpus API. No page numbers are accepted.

Schema example only; these are invented fixture values, not article content:

```yaml
corpus_sources:
  - id: prayer
    kind: quote                 # quote | retelling
    text: Pray with love and care.
    chunk_id: book-5-1
    book_id: 5
    char_start: 18
    char_end: 42
    text_sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    author: Author
    title: Work
    chapter: Prayer             # null when the corpus has no chapter
    translator: Translator      # null for an untranslated work
    source_url: https://example.org/book
```

Body binding: `Pray with love and care.[^corpus-prayer]`. `text` must occur
literally immediately before its marker (whitespace between them is allowed).
Include the entire claim and its attribution in `text`, not just selected words.
Use a separate entry and marker for each occurrence. Do not manually define
these footnotes. Entries require exactly the fields above; IDs are unique,
lowercase Latin letters/digits/hyphens. Ordinary Markdown footnotes still work.
Use plain prose for the supported span; Markdown delimiters inside `text` would
be part of the text compared against the corpus.

## Author workflow

1. Search `POST /api/v1/channels/lampada/search` with query and optional book,
   author, tradition, licence or language filters. Keep the selected hit's
   `chunk_id`, `book.id`, metadata, chapter, offsets and `text_sha256`.
2. Review `/search/context` with the chunk ID and `scope=leaf`. Use a subrange
   of that chunk when it identifies the supporting passage more precisely.
   Offsets count Unicode code points in canonical text, zero-based `[start,end)`.
3. Write short verbatim quotes, or retell the ideas in our own words and
   structure without extra attribution. Name the translator for translations.
   Copy metadata exactly; `chapter` is a chapter, never a printed page number.
4. Run the checker below and review its internal Markdown report with Maria.
   A passing model verdict is evidence assistance, not publication approval.
5. Run `python -m sitegen build` and `python -m sitegen check`; commit article
   source and regenerated `dist/` together. Never commit source paragraphs,
   full books, credentials or review reports.

This implements the article-side rules of Architecture ADR-0018 (2026-10-17):
verbatim attributed quotations of justified length, retellings in our own words,
no views invented for the author, and internal-only corpus fragments. Selecting
a lawful copy, respecting source terms, quotation length and reviewing the
article's overall structure remain editorial responsibilities. The checker
cannot discover every unmarked quotation or prove the legal basis of a book.

## Checker

Install the repository's `requirements.txt`, then:

```bash
export CORPUS_API_URL=http://127.0.0.1:3018
# Inject the channel-ai API_KEY as CORPUS_API_KEY from your private environment.
# Do not put credentials in article sources, arguments or committed files.
export CORPUS_JUDGE_COMMAND='/absolute/path/to/llm-judge --json'
python tools/check_corpus_citations.py \
  content/lampada/articles/<slug>/ru.md --report /tmp/lampada-review.md
```

With no positional paths the checker reads every Lampada article, including
drafts. Files without sources are schema-checked and reported with zero evidence
entries; this is not a claim that their prose has been reviewed. The report
path must be outside this repository because it contains internal source text.
Exit 0 means all declared sources passed; exit 1 means at least one failed or
an API/judge/configuration error occurred; invalid CLI arguments exit 2.

Quotes are matched after NFC, whitespace collapse and typographic quote
normalisation on both sides. Punctuation, word order, case and omissions are
otherwise significant. Matching is bounded by the referenced range plus
`--near` characters per side (default 500, 0..10000), clipped to the API's leaf
section. A matching passage elsewhere in the book does not count.
The checker fetches the full canonical book, recalculates its UTF-8 SHA-256,
compares stored, chunk, context and full-text hashes, and checks the current
chunk identity, range, text, chapter and public attribution metadata. It uses
`/search/chunks`, `/books/{book_id}/text` and `/search/context`; it does not
re-extract books or silently relocate evidence. HTTP 409 is a failed check:
wait for ingestion/migration to finish, inspect the new source and explicitly
refresh the reference. There are no retries or alternate-source substitutions.

## Pluggable LLM judge

Site has no LLM provider configuration. `CORPUS_JUDGE_COMMAND` (or
`--judge-command`) is an executable adapter to the chosen LLM provider. It runs
without a shell, with a 120-second timeout and inherited environment. Provider
URL, model and secret configuration belong to that adapter's private runtime
environment; the checker chooses no provider or model. Use the approved
self-hosted/provider setup from Architecture's model policy. Source passages
are internal: do not send them to an unapproved service.

The adapter receives one UTF-8 JSON object on stdin:

- `instruction`: rubric requiring support for every claim/attribution, our own
  wording/structure, and rejection of extra views, distortion or close paraphrase;
- `article_text`: the full supported span, including attribution;
- `source`: the exact referenced canonical range;
- `source_context`: the bounded neighbouring paragraph(s);
- `author`, `title`, `chapter`: attribution metadata.

The adapter must call an LLM, treating article/source values as untrusted data,
and return **only** JSON on stdout, exiting 0:

```json
{"supported": false, "reason": "The source does not support the attributed claim."}
```

`reason` must be non-empty and `supported` must be a JSON boolean. A nonzero
exit, timeout, missing command, invalid JSON or invalid verdict fails the check.
Write adapter diagnostics to stderr; checker reports do not echo raw adapter
output, which might contain credentials. There is no automatic approval or
heuristic substitute when the judge is unavailable.

## Offline tests

```bash
python -m unittest discover -s tests -p test_corpus_citations.py
```

Tests use a fake corpus API and fake judge, covering exact/distorted quotations,
whitespace/NFC/quotes, wrong meaning, stale/corrupt hashes, identities, ranges,
metadata, HTTP 409/auth, judge errors, reports and sitegen's rendered footnotes.
The existing CI unittest step discovers these tests; CI needs no corpus key,
live corpus access or LLM credentials.
