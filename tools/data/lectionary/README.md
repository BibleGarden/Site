# Daily-reading inputs and verification

Owner decisions: 2026-10-05, ticket 123pfqn1vbq. Publish selectable local audio translations on the ru/uk block, including
Russian Synodal and Ukrainian Khomenko (UBH); open UBH JSON is owner-authorized.
ROC uses Julian fixed feasts/Pascha and the Lukan jump. OCU uses New Julian fixed
feasts, Julian Pascha and no Lukan jump. English has no daily block.

`tables.json` comes from the research prototype prepared on 2026-10-05. Its `meta`
records sources and Synodal reference coordinates. `sitegen/lectionary.py` ports
that prototype, removes silent defaults, validates required tables and keeps
winter sequences within one calculator instance. Only the explicit table for
0–5 winter weeks is supported; unknown sequences fail.

Sources: [Azbyka reading index](https://azbyka.ru/days/p-ukazatel-evangelskih-i-apostolskih-chtenij-na-kazhdyj-den-goda),
[Azbyka calendar](https://azbyka.ru/days/2026-10-05),
[pravoslavie calendar](https://days.pravoslavie.ru/Days/20210125.html),
[OCU 2026 instructions](https://www.pomisna.info/wp-content/uploads/2026/02/bogosluzhbovi-vkazivky-2026.pdf),
[UGCC 2025 calendar](https://ugcc.ua/data/tserkovnyy-kalendar-ugkts-na-2025-rik-5931/),
[UGCC 2026 calendar](https://ugcc.ua/data/tserkovnyy-kalendar-ugkts-na-2026-rik-8059/).
Research snapshots were supplied with the ticket; no source is fetched by the build.
Ponomar/GPL data is not used.

`references.json` preserves each captured date and normalized ranges, including
empty source entries. Azbyka: 2024-01-01 through 2026-10-31 and seven January 2027
dates; pravoslavie: historical windows 2017–2024; OCU: 2026; UGCC: 2025–2026.
The comparison uses the prototype's first Gospel, first composite/Hours component,
or first OT passage. Raw comparison references can include Matins; this limitation
is preserved to reproduce the research baseline, not treated as full daily proof.
Separate `liturgy_refs` for Ukrainian verification select explicitly liturgical
sections and exclude Matins, Vespers, Hours, water blessing and foot washing.
A standalone ordinary Apostle–Gospel pair without a service heading is also
liturgical evidence: OCU prints it on one bare reference line; UGCC prints bare
`Ап.` and `Єв.` lines. This rule requires exactly that pair in the entire day's
parsed readings and no other service heading. Multiple pairs, labelled saints'
readings and incomplete references do not qualify implicitly.
A displayed date is confirmed only when
all computed references occur on that same date in one captured OCU/UGCC source.
Matching a neighbouring day does not confirm a date or alter its readings.
No annual match is extrapolated to an unobserved date. Incomplete parsing is
conservative: it leaves the date `uncertain`.

### Reproducible Ukrainian service extraction

The research `6.24-work/build_reference.py` used `ukrefs.py` to normalize source
references in `6.24-reference-readings.json`. The original implementation then
selected source lines only after a literal `Літ.` heading. That discarded ordinary
weekday pairs such as 2026-10-05: Phil 1:1–7 and Luke 4:37–44 in both calendars.
It also failed to end the Liturgy section at some later service headings.

On 2026-10-06, the offline research snapshots were available under
`/tmp/claude-0/-root-cep/09d308e0-0be1-414a-9259-7a79bb66ca94/scratchpad/`:
`6.24-research.md`, `6.24-lectionary-spec.md`, `6.24-reference-readings.json`,
and `6.24-work/{ocu-2026,ugcc-2025,ugcc-2026}-raw.json`.
`source-readings.json` now retains their Ukrainian source lines and per-line
normalized ranges, with the capture date, source URLs and research snapshot hash.
Numerical parsing limitations are preserved, including unparsed OT/composite
components and four UGCC ranges lacking a chapter. They cannot implicitly confirm
a pair. The snapshot is research evidence, not a newly fetched calendar.

`tools/build_lectionary_references.py` classifies those lines without a network,
database, calculator or substitution of the day's broad `refs`. Date order and
the flattened comparison references must match `references.json`; a change fails
explicitly. Service headings control the section; standalone pair recognition
applies only when there is no service heading. Tests reproduce all committed
evidence and exclude other services even if they contain an Apostle–Gospel pair.

```bash
.venv/bin/python tools/build_lectionary_references.py
.venv/bin/python tools/build_gospel_today.py --start-year 2026 --end-year 2030
.venv/bin/python -m sitegen build
```

Measured 2026-10-06 by counting `days[*].uncertain` in the annual uk schedules,
before/after this extraction fix:

| Year | Before | After | Dates |
|---|---:|---:|---:|
| 2026 | 245 | 73 | 365 |
| 2027 | 365 | 365 | 365 |
| 2028 | 366 | 366 | 366 |
| 2029 | 365 | 365 | 365 |
| 2030 | 365 | 365 | 365 |

2026-10-05 is confirmed by both `ocu` and `ugcc`. The remaining 73 dates require
more complete source parsing or liturgical evidence; the standalone-pair rule
does not prove them. No Ukrainian 2027–2030 source dates are captured, so all those
dates remain uncertain. Empty `liturgy_refs`: OCU 242 → 141 of 365; UGCC
527 → 121 of 730. Broad comparison `refs` are unchanged.

Rechecked on 2026-10-06 by `tools.build_gospel_today.accuracy`, using the committed
reference data and the ported calculator. Every count below is identical before
and after the extraction fix (OCU 91.24%, UGCC 92.23% exact):

| Source/calendar | Exact | Adjacent | Mismatch | Empty source | Threshold |
|---|---:|---:|---:|---:|---|
| Azbyka/ROC | 993/1042 (95.30%) | 40 | 9 | 0 | ≥95% exact; 1033/1042 (99.14%) ≥99% with adjacent |
| pravoslavie/ROC | 1056/1133 (93.20%) | 39 | 38 | 59 | ≥93% exact |
| OCU/New Julian | 302/331 (91.24%) | 0 | 29 | 34 | ≥91% exact |
| UGCC/New Julian | 617/669 (92.23%) | 1 | 51 | 61 | ≥92% exact |

The tests pin these denominators, reported counts and thresholds. Mismatches
include saints' readings/transfers, omitted ordinary readings and source parsing
issues; the metric does not assert correctness of every Apostle or secondary
passage. Known cases test those independently: Pascha, Lukan jump, early-Pascha
repeats, Forefathers exchange, winter repeats, Zacchaeus, Nativity/Epiphany eves,
Royal Hours, Lent, Holy Friday composite readings and Ascension.

`verses.json` is exported from local `cep_public` in a read-only transaction.
It contains required chapters in canonical book order and their actual translation
coordinates, text and joined-verse bounds. DB Epistle IDs are converted using the
existing `SOURCE_NT` mapping. No text is reconstructed from HTML or another
translation. Malformed/duplicate data and unknown blank text fail. Missing source passages
are explicitly unavailable, never supplied from another translation. UBH Romans
14:24–26 maps explicitly to 16:25–27; the public label uses the target coordinates.
Cross-chapter ranges enumerate each translation's full intervening chapters;
Synodal 2 Corinthians 11:32 contains the material split into UBH 11:32–33.
Romans 16:23–24 differs textually between Synodal and UBH; text is printed exactly
as stored, without inserting the blessing absent from UBH.

No saints' readings or related transfers, Matins readings or full Typikon of rare
Annunciation/Holy Week coincidences are computed. Ukrainian future winter repeats
are projected, visibly unconfirmed. ROC R=1 is partly verified and marked uncertain.
Build range is explicit: 2026–2030. Daily arithmetic accepts 1901–2098;
Paschalion accepts 1900–2099. Extend the committed output yearly, refreshing dated
Ukrainian evidence when official calendars become available.


## Khomenko Matthew 23:14–15

Investigated on 2026-10-05 with read-only SQL in both local databases and source
HTTP reads. `cep_admin` and `cep_public` have identical Mt 23:12–16 text/HTML and
flags for UBH, SYN and NPU. UBH 23:14 contains the proselyte saying numbered 23:15
in SYN/NPU; UBH 23:15 is empty, `verse_number_join=0`. No text manual-fix table
exists: `voice_manual_fixes` is for audio begin/end only, with no UBH Mt 23:12–16
fixes. The parser JSON reproduces the same representation.

The documented text source [bible.by](https://bible.by/ubh/40/23/) returned HTTP 200
and has text under 14, an empty 15 and unchanged 16. An independent Khomenko
publication at [TrueChristianity](https://www.truechristianity.info/ua/biblia/matthew_ukr.php)
explicitly labels the same proselyte saying **14–15**. This is a combined range,
not lost proselyte text and not grounds for inserting SYN/NPU's widow-house saying.
[bible.net.ua](https://bible.net.ua/translation/ubh/40/23/) also reproduces 14/text,
15/empty. The documented heading source yogo-slovo.org could not resolve; it was
not used as evidence. No manuscript-critical claim beyond these publications is
made.

`normalize_known_joins` recognizes **only** the exact empty UBH 40:23:15 record
with a verified 40:23:14 neighbour and compatible join bounds, emits one verse
14–15 with the unchanged neighbour text, and records `ubh-matthew23-14-15` in the
export snapshot. Changed text, a missing neighbour or incompatible bounds fails;
unknown empty records still fail; verified WEB textual-variant omissions
make affected passages explicitly unavailable. Database records are not changed.
Tests assert the merged text appears once and unknown gaps cannot use this rule.

The complete 2026–2030 scan covered 768 unique computed references per calendar,
including Apostle, OT, Hours and composite readings, in **both** local databases.
After explicit book/ Romans versification mapping, the sole empty/missing required
coordinate was UBH Mt 23:15, accounted for by the verified merge above. SYN had
no required empty/missing coordinates. Other corpus gaps outside these pericopes
were not changed or included in this claim.


## Source bundle and chapter public sizes

Generation: 2026–2030, 1,826 dates per calendar, 768 distinct references in their
union. The fingerprinted source has ten annual schedules, seven passage
dictionaries and a manifest. Public schema 3 publishes no daily passage files:
120 monthly reference schedules and 314 required chapters per translation.

Measured 2026-10-06 after build using file byte lengths in
`dist/bible-garden/data/gospel-today/`, excluding filesystem allocation and
unrelated static assets:

| Type | Files | Total UTF-8 bytes | Largest file |
|---|---:|---:|---:|
| Monthly schedules | 120 | 1,115,333 | 11,616 |
| Translated chapters with all offered voices | 2,198 | 12,006,025 | 15,764 |
| **All public data** | **2,318** | **13,121,358** | **15,764** |

Paths: `schedule/<ru|uk>/<YYYY>/<MM>.json`,
`text/<translation>/<canonical-book:02>/<chapter:02>.json`.
Each chapter's text and timecodes occur once across days/calendars; monthly
schedules contain only day metadata and Scripture coordinates. See README for
strict validation, range assembly, API numbering and cache behavior.

Cold-page JSON bytes, including one monthly schedule, excluding MP3 streams and
other page assets. Measured by deriving each day's unique mapped chapter keys
and summing those files plus its schedule; Chromium asserts the matching request
set (3 requests on October 5; 6 on the composite Holy Thursday reading).

| Translation | ru Oct 5 | uk Oct 5 | ru Apr 9 | uk Apr 9 |
|---|---:|---:|---:|---:|
| syn | 23,070 | 24,988 | 66,863 | 66,832 |
| bti | 23,258 | 25,681 | 67,532 | 67,501 |
| ubh | 22,781 | 24,194 | 63,243 | 63,212 |
| npu | 22,726 | 24,199 | 64,313 | 64,282 |
| bsb | 20,069 | 20,815 | 52,215 | 52,184 |
| webus | 19,199 | 19,938 | 48,411 | 48,380 |
| webbe | 19,201 | 19,937 | 48,415 | 48,384 |

## Translation and aligned-audio coverage

Measured 2026-10-05 from the local read-only cep_public exports and validated
768-reference union for this horizon. Counts are complete **distinct passages**,
not dates, individual verses or claims about whole Bible coverage.

| Translation | Complete text passages | Narrator: complete aligned passages |
|---|---:|---|
| syn | 768 / 768 | prudovsky: 768; bondarenko: 738 |
| bti | 754 / 768 | prozorovsky: 748 |
| ubh | 766 / 768 | kozlov_uk: 766 |
| npu | 673 / 768 | npu_uk: 673 |
| bsb | 751 / 768 | bsb_souer: 751; bsb_david: 751 |
| webus | 764 / 768 | winfred_henson: 764 |
| webbe | 764 / 768 | web_british: 763 |

The active registry is 7 translations / 9 voices. NPU covers Psalms and NT only.
Bondarenko lacks 1–2 Chronicles, Song of Songs and Isaiah and includes music.
Kozlov excludes Esther 11–12, Daniel 13–14. Missing alignment marks the complete
passage unavailable for that voice while retaining its text and other voices.
The timecode snapshot contains 83,240 requested-chapter verse records, including
9 explicitly unavailable intervals: Bondarenko 2, Prozorovsky 6, WEB British 1.
Their original invalid bounds are retained under `invalid`; public audio is null.
Nonfinite values, unknown voices/coordinates and duplicates are rejected.

Text/numbering availability is independent: BSB/WEB textual omissions and absent
verses remain absent; no partial passage or translation substitution is allowed.
The verified WEB empty records at Luke 17:36; Acts 8:37, 15:34, 24:7; Romans 16:25
are excluded from the source text snapshot, making any requiring passage unavailable.
Unknown blank records still fail. Source joins with reordered/negative coordinates
are recorded in `verses.json.numbering`; affected chapters cannot be rendered.

The calculator's reference system is Synodal. No Psalm occurs in the current
tables. A future Psalm reference is unavailable until a reviewed mapping from
Synodal/Greek coordinates through the local `psalm_verse_mappings` canonical
space to the selected translation is implemented. Identity would be wrong for
Hebrew chapter numbers and Khomenko's numbered headings. UBH Joel/Malachi
chapter differences are likewise unavailable rather than guessed. UBH Romans
and Matthew joins use the explicit verified mappings described above.

`export_gospel_timecodes.py` reads only local cep_public with the same read-only
transaction helper as the text export. It compares the active registry exactly
with `EDITIONS`, keeps only snapshot coordinates, and exports DB times/book names.
It never reads recordings or changes database rows. Normal regeneration/build
use committed inputs and SHA-256 checks; no database/network calls occur.
