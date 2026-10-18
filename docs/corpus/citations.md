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
    chapter: 'II — 3. Prayer'   # exact API citation_label; null for an empty label
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

`chapter` is a copy of the API's complete, human-readable **`citation_label`**,
including native number/title and part/volume when supplied. It is independent
of the API's structural `chapter`. There is no second article field. Copy the
label verbatim; do not compose, translate or shorten it. The API's empty string
means there is no proven locator: store **`chapter: null`**, and the footnote
omits that component. Missing/null/whitespace-only API labels are errors, never
an invitation to substitute a structural chapter, section path or book title.
The offline site only escapes and displays this ready label; it calls no API.

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

For topic selection, chapter research, Maria's plan approval and the ru/en/uk
editorial cycle, start with [the article workflow](article-workflow.md). The steps
below describe the evidence format and verification within that cycle.

1. Search `POST /api/v1/channels/lampada/search` with optional filters. Keep the
   hit's chunk ID, book ID, metadata, citation_label, offsets and SHA-256.
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
The article's `chapter` must match the chunk's `citation_label` (empty string
maps to null); leaf context must return that same label. Structural `chapter`
is never used for this comparison.

## Reanchor after a corpus migration

Use `tools/reanchor_corpus_sources.py` only after the maintenance window has
finished, the new index version is confirmed by the corpus operator, and the
API serves the migrated corpus. The channel API does not expose `index_version`;
a listening port alone does not prove that reindexing is complete. For content
branches, first merge the tooling PR, then rebase each branch on fresh `main`.
Keep old snapshots unchanged. `--snapshots` names the **backup root**, containing
`data/lampada/texts/book_<id>.json` and `.txt` for every referenced book.

```bash
python tools/reanchor_corpus_sources.py \
  content/lampada/articles/<slug>/ru.md \
  --snapshots /root/backups/channel-ai-12.11-20261018 \
  --report /tmp/lampada-reanchor.json
# Review the private JSON report, then explicitly apply it:
python tools/reanchor_corpus_sources.py --apply /tmp/lampada-reanchor.json
python tools/check_corpus_citations.py \
  content/lampada/articles/<slug>/ru.md --report /tmp/lampada-review.md
```

Multiple explicit article paths share cached book/chunk reads within a report.
Report mode writes no articles. Its JSON records article paths, file SHA-256,
old/new anchors and `ready`/`manual` outcomes; it contains private metadata and
must stay outside git. Existing reports are never overwritten. Exit 0 means
every source is ready (or application succeeded); exit 1 means a manual case
or error; invalid arguments exit 2.

For each source, the tool checks the old sidecar/text hash and article range.
If canonical text is unchanged, offsets stay fixed. Otherwise, the **entire
old exact fragment** must have one unambiguous match in the new text, counting
overlapping matches. Quotes also require `original` inside both precise ranges
using the checker's normalization. No fuzzy matching, sentence substitution,
range splitting or prose edits are allowed. Removed/edited/repeated passages,
changed source-edition metadata, or a range without one containing chunk go to
manual review. Chunk IDs are enumerated from `/books`' `chunks_count` using
channel-ai's `book-{book_id}-{zero_based_index:04d}` contract, fetched in batches
of at most 100 and checked against canonical text; semantic search is not used.

Application refuses any report with manual cases. It checks every article's
file SHA against the report, recreates the plan against live chunks/text/leaf
context and old snapshots, and requires an identical result. It then stages and
validates every article before replacement, checking SHA again before writes.
Each file replacement is atomic; the set of files is not a filesystem
transaction. Only `chunk_id`, `char_start`, `char_end`, `text_sha256`, and
`chapter` scalars change; body and other YAML remain byte-for-byte intact.
Do not edit articles concurrently. If an article or corpus changed, make a new
report; do not edit the saved plan. Resolve manual cases editorially in a new
review cycle, never by making the migration tool guess.

After applying, run the checker **with its cache enabled** and require exit 0;
reanchoring alone is not an evidence verdict. Rebuild the relevant draft with
`python -m sitegen preview`, then restart its preview service. Commit anchor
changes in the corresponding content branch; `.preview/` output is ignored.

## LLM judge adapter

The default `tools/corpus_judge_claude.sh` uses the installed, authenticated
Claude CLI with Opus fixed in the adapter:

```bash
claude -p --model opus --output-format json --tools "" \
  --safe-mode --setting-sources "" --strict-mcp-config --no-session-persistence \
  --json-schema <schema>
```

Safe mode disables CLAUDE.md and custom skills/plugins/hooks; setting sources and
configured MCP servers are disabled, and sessions are not persisted. Managed
policy, inherited environment and remote provider configuration still apply;
bump `--judge-version` when those change. Authentication remains private.

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
yield UNSTABLE. One shared pool limits simultaneous judge calls across fragments
and their runs (`DEFAULT_JUDGE_WORKERS = 6`, positive `--judge-workers` override).
All articles are prepared before collecting results; corpus validation stays
serial. Reports retain article order and run-number order,
independently of completion order. Every scheduled call is awaited and reported;
any error makes that fragment ERROR, and its partial set is not cached. Other
fragments continue. Calls are never retried or replaced. Unexpected programming
exceptions propagate. Exact untranslated quotes use deterministic checks.

Each adapter starts in its own POSIX process group. Timeout cleanup kills that
whole group and waits before freeing its worker slot. Cleanup communication is
bounded to five seconds; exceeding it aborts the run with an explicit cleanup
error. Ctrl-C, SIGTERM, SIGHUP or an uncaught exception cancels queued work, kills
active groups and joins their workers. CLI signal handlers are restored on exit.
Identical evidence keys share one review across the run, including across articles.
A cache-write error marks ERROR while preserving votes and trusted source context.

Reports list all completed votes, categories and reasons, the run count, and
final PASS/FAIL/UNSTABLE/ERROR counters plus invalid-article count. Any FAIL,
UNSTABLE, ERROR or invalid article exits 1. Missing credentials also fail. Corpus response objects and required field types
are validated at the API boundary; malformed replies mark the fragment ERROR.
Adapter diagnostics stay on stderr; raw output is not echoed into reports.

## Judge verdict cache

The CLI stores complete PASS/FAIL/UNSTABLE vote sets in
`~/.cache/lampada-citation-judge`; override with `--cache-dir` outside the repo.
ERROR and partial sets are never stored. Records contain private explanations:
do not commit or publish them. New directories/files use 0700/0600. Writes use
a temporary file + rename, without per-key locks or alternative cache locations.

Keys cover fragment text, kind, original/translation, canonical range text and
full-book hash, offsets, book/chunk identity, attribution, exact criteria, run
count, adapter SHA-256/arguments, bundled code/schema and Claude CLI version.
Opus and its fixed flags are part of the adapter fingerprint. Executable paths
are excluded so identical worktrees share votes; resolving a bundled-adapter
symlink still includes `claude --version`. Unavailable/invalid version discovery
is an error. Custom adapters need no Claude, but must bump `--judge-version`
(default `1`) for changed wrapper dependencies or hidden configuration.

Each run revalidates the corpus before using cached votes. Invalid, incomplete,
duplicate-key or corrupt records fail explicitly: repair or remove the named
record. Reports mark `Cache: HIT`/`MISS`, retain votes/reasons and count judge
calls and cached fragments. In-process callers opt in with a `JudgeCache`.

Regular checks, including the final review, reuse complete cached verdicts for
unchanged evidence and judge configuration. Use `--no-cache` for diagnostics
(for example, suspected cache corruption): no reads, writes or fingerprinting.

```bash
python tools/check_corpus_citations.py content/lampada/articles/<slug>/{ru,en,uk}.md \
  --no-cache --report /tmp/lampada-diagnostic-review.md
```


## Offline tests

```bash
python -m unittest discover -s tests -p 'test_corpus*.py'
```

Fake corpus, fake judge and a fake Claude executable cover exact/distorted and
translated quotes, wrong retellings, hashes/ranges/metadata, caching, punctuation,
localized footnotes, reports, CLI adapter errors, strict verdict/category
validation, configurable independent runs, unanimous PASS/FAIL, disagreement
reports, category-derived verdicts,
schema arguments, structured-output validation, duplicate-key rejection, errors
without checker retries, and
Lampada-only front matter.
Cache tests cover reuse with zero calls, one edited fragment, prompt/adapter/run
invalidation, preserved FAIL/UNSTABLE explanations, ERROR exclusion, canonical
revalidation, corrupt/unwritable records, private paths and `--no-cache`.
Delayed fake judges verify the shared worker limit across articles/runs,
deterministic reports, deduplicated reviews and preserved error/peer results.
Real subprocess fixtures verify Ctrl-C queue cancellation, descendant termination
and timeout cleanup before a worker slot is reused, SIGTERM/SIGHUP cancellation,
bounded cleanup failure and malformed corpus replies.
Existing CI discovers these tests without live API calls or credentials.
