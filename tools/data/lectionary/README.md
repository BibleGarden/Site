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
sections and exclude Matins and Vespers. A displayed date is confirmed only when
all computed references occur on that same date in one captured OCU/UGCC source.
Matching a neighbouring day does not confirm a date or alter its readings.
No annual match is extrapolated to an unobserved date. Incomplete parsing is
conservative: it leaves the date `uncertain`.

Measured on 2026-10-05 by `tools.build_gospel_today.accuracy`, using the committed
reference data and the ported calculator:

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
Build range is explicit: 2026–2027. Daily arithmetic accepts 1901–2098;
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


## Source bundle and daily public sizes

Current generation: 2026–2027, 730 dates, 766 unique references across the union
of both calendars. Sources are one annual schedule per page language/year,
one passage dictionary per text translation and a fingerprint manifest.
Public schema 2 shares the two calendars in each dated translation file:
`dist/bible-garden/data/gospel-today/<YYYY>/<MM>-<DD>/<translation>.json`.
Only the selected translation is fetched; narrator changes reuse its timings.
No dictionaries, annual files, snapshot or manifest are public. No audio files
are added. README documents the queue, API numbering and preview configuration.

Measured 2026-10-05 by `daily_files(load_bundle())`: byte lengths of compact UTF-8
payloads; `statistics.median`/`max`, excluding allocation and other static assets.
These 5,110 JSON files are the entire public `data/` tree in this worktree.

| Translation | Files | Total bytes | Median bytes | Largest bytes |
|---|---:|---:|---:|---:|
| syn | 730 | 5,183,399 | 6227.5 | 23,398 |
| bti | 730 | 5,170,529 | 6220.5 | 23,357 |
| ubh | 730 | 4,829,697 | 5822.5 | 21,893 |
| npu | 730 | 4,405,064 | 5516 | 22,340 |
| bsb | 730 | 3,824,331 | 4586.5 | 17,652 |
| webus | 730 | 3,621,823 | 4331.5 | 16,163 |
| webbe | 730 | 3,616,731 | 4328 | 16,141 |
| **All public data** | **5,110** | **30,651,574** | **5,361** | **23,398** |

Content bundle: 13,244,802 bytes (11 data files + manifest).
JSON source inputs: 14,775,627 bytes (tables, comparisons, verses,
timecodes and book names). These sources remain offline, not published.
Unconfirmed computed dates: ru 0, uk 610 of 730 each. Regeneration
never removes uncertainty by extrapolating evidence.

## Translation and aligned-audio coverage

Measured 2026-10-05 from the local read-only cep_public exports and validated
766-reference union for this horizon. Counts are complete **distinct passages**,
not dates, individual verses or claims about whole Bible coverage.

| Translation | Complete text passages | Narrator: complete aligned passages |
|---|---:|---|
| syn | 766 / 766 | bondarenko: 736; prudovsky: 766 |
| bti | 752 / 766 | prozorovsky: 746 |
| ubh | 764 / 766 | kozlov_uk: 764 |
| npu | 671 / 766 | npu_uk: 671 |
| bsb | 749 / 766 | bsb_david: 749; bsb_souer: 749 |
| webus | 762 / 766 | winfred_henson: 762 |
| webbe | 762 / 766 | web_british: 761 |

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
