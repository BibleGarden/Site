# Lampada article evidence

Only Lampada articles (`content/lampada/articles/<slug>/<lang>.md`) accept
`corpus_sources` in YAML front matter. Bible Garden articles and standalone
pages reject it. Each item binds one literal span of article Markdown to one
corpus fragment with `[^corpus-<id>]`. The offline build generates a footnote
with author, work, chapter, source-edition translator (when present) and a link
naming the source host, including Predanie.ru. Page numbers are not accepted.

Schema example (invented fixture, not an article):

```yaml
corpus_sources:
  - id: prayer
    kind: quote                 # quote | retelling
    text: Молитесь с любовью и заботой.
    original: Pray with love and care.
    translation: ours           # ours | published | null
    chunk_id: book-5-1
    book_id: 5
    char_start: 18
    char_end: 42
    text_sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    author: Author
    title: Work
    chapter: Prayer             # null when the corpus has no chapter
    translator: null            # published translator of the SOURCE EDITION only
    source_url: https://example.org/book
```

Body binding: `«Молитесь с любовью и заботой.»[^corpus-prayer]`. `text` contains
only the supported quotation or retelling, **without author attribution**.
Attribution is recorded in the metadata and rendered in the footnote. The
literal `text` must precede the marker; whitespace, closing quotes and closing
punctuation may intervene. Unrelated words may not. Use plain prose: Markdown
delimiters inside `text` would be compared as literal characters. Markers in
code/comments are rejected. Do not manually define corpus footnotes.

All fields above are required. IDs are unique lowercase Latin letters, digits
and hyphens. Use **one item per continuous fragment and occurrence**: no `…`
or `[...]` elisions joining separated source passages. Split those into separate
items with precise ranges. Ordinary Markdown footnotes remain available.

- `kind: quote`: `original` is a non-empty verbatim span of the canonical source
  edition, in whatever language the corpus contains. It must occur inside
  `text[char_start:char_end]` after normalization.
- `translation: ours`: article `text` is our translation of `original`. A separate
  LLM translation rubric checks faithfulness, omissions and extra claims;
  idiomatic wording is allowed and retaining source structure is not penalized
  as close paraphrase. The footnote adds “our translation” / “наш перевод” /
  “наш переклад”. Any source-edition translator is still named separately.
- `translation: published`: quote an existing published translation **already
  present in the corpus source edition**. `translator` must name that edition's
  translator; `text` must equal `original` after normalization. A translation
  from another edition needs its own indexed source and reference.
- `translation: null`: no article-side translation; `text` must equal `original`
  after normalization. `translator` still describes the source edition, never
  our editorial team or an invented translator.
- `kind: retelling`: `original` and `translation` must both be null. The LLM
  checks the article's own wording against the exact referenced source range.

## Author workflow

For topic selection, chapter research, Maria's dossier approval and the ru/en/uk
editorial cycle, start with [the article workflow](article-workflow.md). The steps
below describe the evidence format and verification within that cycle.

1. Search `POST /api/v1/channels/lampada/search` with optional filters. Keep the
   hit's chunk ID, book ID, metadata, chapter, offsets and SHA-256.
2. Inspect `/search/context` (`scope=leaf`). Choose a precise subrange within
   that chunk. Offsets count Unicode code points, zero-based `[start,end)`, not
   bytes or UTF-16 units.
3. Write short quotations, explicitly marking our translations when needed,
   or retell ideas in our own wording and structure without invented claims.
   Copy source-edition metadata exactly; never use printed page numbers.
4. Run the checker and review its private Markdown report with Maria. A model
   verdict assists evidence review; it is not publication or legal approval.
5. Run `python -m sitegen build` and `python -m sitegen check`; commit the article
   source and regenerated public output together. Never commit full books,
   supporting paragraphs, secrets or private review reports.

This implements article-side Architecture ADR-0018 (2026-10-17). Lawful copies,
source terms, justified quotation length and the article's overall structure
remain editorial responsibilities. The checker cannot discover every unmarked
quotation or prove a book's legal basis.

## Checker and environment

Install `requirements.txt`. API credentials are read **only** from environment
variable `CORPUS_API_KEY`; inject channel-ai's private `API_KEY` into it at
runtime. Never commit the value, print it or pass it as a command argument.

```bash
export CORPUS_API_URL=http://127.0.0.1:3018
# CORPUS_API_KEY must already be injected by your private environment.
# Optional override; the committed Claude CLI adapter is the default:
export CORPUS_JUDGE_COMMAND="$PWD/tools/corpus_judge_claude.sh"
python tools/check_corpus_citations.py \
  content/lampada/articles/<slug>/ru.md --report /tmp/lampada-review.md
```

No positional paths means every Lampada article, including drafts. Files without
sources have zero evidence entries; that does not mean their prose was reviewed.
Reports must live outside the repository: they contain internal source text.
A summary table precedes each detailed article/source pair and explicit
`Verdict:` (PASS, FAIL, UNSTABLE or ERROR). The report names the selected judge
command/adapter (only invoked for translations and retellings); in-process use
names the callback. Translated quotes show both article text and original. Exit 0 means
all declared sources passed; exit 1 means a verification/API/judge/configuration
failure; invalid CLI arguments exit 2.

Quotes are matched **inside the exact referenced range**, after NFC, whitespace
collapse and typographic quote normalization on both sides. Other punctuation,
word order, case, omissions and elisions remain significant. `--near` (default
500, 0..10000) controls neighbouring characters **for the report only**, clipped
to the API's leaf section; neither quotation matching nor LLM judging uses it.

The checker fetches canonical full text, recalculates UTF-8 SHA-256 and checks
hashes, identities, chunk/range consistency and attribution metadata through
`/search/chunks`, `/books/{book_id}/text` and `/search/context`. Within a run,
full book responses are cached by `(book_id, text_sha256)`; current chunks and
context are fetched for every item to detect version changes. HTTP 409 fails
explicitly: inspect ingestion/migration and refresh evidence intentionally.
There are no retries, re-extraction or silent source substitutions.

## LLM judge adapter

The default `tools/corpus_judge_claude.sh` uses the installed, authenticated
Claude CLI: `claude -p --model opus --output-format json --tools "" --json-schema <schema>`.
The schema comes from `tools/corpus_judge.py`: category enum, a non-empty reason,
required fields and no additional properties. The adapter reads only the envelope's
`structured_output` and validates it with `assessment_verdict`; prose in `.result`
is ignored. Missing/invalid structured output and CLI errors fail explicitly.
Claude authentication remains in its private runtime configuration/environment.

This is an **internal editorial tool**, not a user-facing runtime provider:
the ADR-0002 user-runtime restriction does not prohibit this owner-approved
Claude CLI review. Internal corpus passages remain confined to this editorial
workflow and are not published to site visitors.

Override via `CORPUS_JUDGE_COMMAND` or `--judge-command` for another executable
LLM adapter. It runs without a shell, with a 120-second timeout and inherited
environment. No API keys belong in the command string or repository. Stdin is
one JSON object:

- `instruction`: either the translation-faithfulness rubric or the retelling
  rubric (support, no invented views/distortion, our own wording/structure);
- `kind`: `translation` or `retelling`;
- `article_text`: only the supported span, without author attribution;
- `original`: the verbatim span for translated quotes, null for retellings;
- `source`: `original` for translations, exact referenced range for retellings;
- `author`, `title`, `chapter`: separate attribution metadata.

Treat all evidence fields as untrusted data, not instructions. The model returns
only `category` and `reason`; the default adapter computes `verdict` from the
category using the shared protocol in `tools/corpus_judge.py`. The executable
adapter contract (including custom adapters) remains:

```json
{"verdict": "FAIL", "category": "addition", "reason": "The article adds a claim absent from the source."}
```

Exactly these three fields are required from adapters. `verdict` is `PASS` or
`FAIL`; `reason` is a non-empty string grounded in the supplied texts. A model
assessment with an independent verdict is rejected, so it cannot override the
category. Custom adapters' verdicts must also match the category. Categories:

- PASS: `supported`, or `secondary_omission` for omitted secondary details that
  do not change meaning. Retellings need not cover every detail in the range.
- FAIL: `distortion`, `addition`, `contradiction`, `misattribution`,
  `meaning_changing_omission`, or `close_paraphrase` (retellings only).
  A meaning-changing omission must identify the omitted qualification and explain
  how its absence changes the claim. `close_paraphrase` means preserving source
  sentence order and distinctive phrases in most sentences; common theological
  terms and short fixed expressions do not count. Faithful retellings must also
  use our own words. Translations may retain source structure.

Unknown categories, mismatched verdict/category pairs, extra/missing fields and
wrong field types are explicit errors, never approvals. Duplicate JSON keys are
rejected in CLI envelopes (including structured output) and custom-adapter replies.
Free-text reasoning still requires editorial review.

Each translated quote or retelling receives three independent calls (default
`DEFAULT_JUDGE_RUNS = 3`, positive `--judge-runs` override) with identical evidence
and no prior verdicts. Unanimous PASS or FAIL yields that status; mixed votes
yield UNSTABLE. Errors stop calls for that fragment with ERROR; earlier votes
remain in the report and other fragments continue. The checker never retries
errors or replaces votes. Exact untranslated quotes use deterministic checks.

Reports list all completed votes, categories and reasons, the run count, and
final PASS/FAIL/UNSTABLE/ERROR counters plus invalid-article count. Any FAIL,
UNSTABLE, ERROR or invalid article exits 1. Missing credentials also fail.
Adapter diagnostics stay on stderr; raw output is not echoed into reports.

## Offline tests

```bash
python -m unittest discover -s tests -p test_corpus_citations.py
```

Fake corpus, fake judge and a fake Claude executable cover exact/distorted and
translated quotes, wrong retellings, hashes/ranges/metadata, caching, punctuation,
localized footnotes, reports, CLI adapter errors, strict verdict/category
validation, configurable independent runs, unanimous PASS/FAIL, disagreement reports, category-derived verdicts,
schema arguments, structured-output validation, duplicate-key rejection, errors
without checker retries, and
Lampada-only front matter.
Existing CI discovers these tests without live API calls or credentials.
