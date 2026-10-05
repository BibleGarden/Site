# Daily-reading inputs and verification

Owner decisions: 2026-10-05, ticket 123pfqn1vbq. Publish Russian Synodal and
Ukrainian Khomenko (UBH) passage texts, with open UBH JSON authorized by the owner.
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
translation. Missing, blank or duplicate data raises an error. UBH Romans
14:24–26 maps explicitly to 16:25–27; the public label uses the target coordinates.
Cross-chapter ranges enumerate each translation's full intervening chapters;
Synodal 2 Corinthians 11:32 contains the material split into UBH 11:32–33.
Romans 16:23–24 differs textually between Synodal and UBH; text is printed exactly
as stored, without inserting the blessing absent from UBH.

No saints' readings or related transfers, Matins readings or full Typikon of rare
Annunciation/Holy Week coincidences are computed. Ukrainian future winter repeats
are projected, visibly unconfirmed. ROC R=1 is partly verified and marked uncertain.
Build range is explicit, initially 2026–2030. Daily arithmetic accepts 1901–2098;
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
other empty/missing verses still fail. Database records are not changed.
Tests assert the merged text appears once and unknown gaps cannot use this rule.

The complete 2026–2030 scan covered 768 unique computed references per calendar,
including Apostle, OT, Hours and composite readings, in **both** local databases.
After explicit book/ Romans versification mapping, the sole empty/missing required
coordinate was UBH Mt 23:15, accounted for by the verified merge above. SYN had
no required empty/missing coordinates. Other corpus gaps outside these pericopes
were not changed or included in this claim.


## Committed asset sizes

Measured on 2026-10-05 by summing file byte lengths after
`python tools/build_gospel_today.py --export-local --start-year 2026 --end-year 2030`:

| Data | UTF-8 bytes |
|---|---:|
| Both calendars' ten annual schedules | 655,303 |
| Both translations' text dictionaries | 3,843,139 |
| Manifest | 1,309 |
| Total public JSON | 4,499,751 |
| Committed source JSON (tables, references, verse snapshot) | 4,783,966 |

There are 1,826 dates and 768 unique passages per language. The browser downloads
one annual schedule and its language's text dictionary; each passage is stored
once per translation, including across years. Independently gzip-compressing the
six ru files yields 530,173 bytes and the six uk files 549,275 bytes (Python
`gzip.compress`, `mtime=0`; these are measurements, not additional committed files).
Of the 1,826 Ukrainian dates, 1,706 remain unconfirmed by the captured same-day
liturgical evidence. Six ROC dates carry the prototype's R=1 uncertainty. Annual
regeneration alone does not remove these flags; add dated official evidence.
