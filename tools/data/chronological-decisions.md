# Bible Garden chronological sequence: editorial decisions (version 1)

Status: draft for owner and independent editorial review. Source comparison and
chapter checks dated **2026-10-04**. References use English chapter numbering (BSB),
Hebrew numbering specifically for Psalms, and USFM book codes. Thus MAL has
four chapters and JOL three; this is not the Hebrew chapter scheme for all books. This is a reading order of
whole chapters, not a claim that every verse follows its historical predecessor.

## Method

Three complete public schemes were examined: **BLB** (Blue Letter Bible),
**BTTB** (Back to the Bible, 2025 PDF), and **NLT** (Tyndale chronology published
with permission by Bible In A Year Online). URLs, retrieval date and SHA-256
of the actual PDFs are in `chronological-sequence.json`. PDF reference tables
were inspected with `pdftotext -layout`; the NLT PDF's broken text encoding was
normalized locally before comparison. NLT's verse-level rearrangements were
compared as historical contexts, not mechanically rounded into whole chapters.
**R** is Robertson's 1922 Gospel harmony, Parts II–XIV, used only to check
parallel episodes. It is not a fourth whole-Bible scheme.

BTTB and BLB share much of their outline and many daily selections; their
independence is unknown. Agreement between them is not two independent votes.
Crossway's current [catalog](https://www.esv.org/learn-more/reading-plans/)
contains an eight-era chronological description inside an HTML comment, but no
usable chapter schedule was retrieved. Crossway and Reese therefore contribute
no chapter-placement evidence. No unsupported source agreement is asserted.

The shared historical backbone (Genesis, exodus, settlement, monarchy,
exile/return, Jesus, Acts) supplies the order where all three schemes agree.
Explicit biblical headings and narrative connections settle the finer choices.
For disputed Old Testament placements, the chosen option mostly follows
**NLT/Tyndale** (especially Job, Moses’ Psalm, wisdom, late prophets, Jeremiah,
Daniel and the rebuilding sequence). This is a synthesis strongly informed by
that option, not an independent reconstruction of every disputed date.
Biblical dating controls the revisions after the two reviews of commit 9baff89.
Some Gospel runs coincide with BLB because whole-chapter harmony offers few
ways to retain the same event phases. Late-letter ordering is less constrained;
we now use NLT’s equally defensible 2TI → HEB → 1PE and move JUD after the
Johannine letters, rather than retain BLB’s 68-chapter PHP-to-REV run.
John’s trial account precedes the Synoptic crucifixion chapters and LUK 24
precedes MRK 16; these alternatives retain the same phases without copying
the entire BLB passion/resurrection run. No chronology was worsened to differ.
Consecutive chapters are grouped by our own narrative boundaries. No publisher's
365-day allocation, headings, commentary or complete ordering was imported.
BLB/BTTB's speculative placement of nearly every Psalm is deliberately avoided;
NLT's genealogy fragments and verse harmony are not reproduced.

### Identical BLB runs after review

Measured on 2026-10-04 by expanding both sequences to chapter pairs, ignoring
segment/day boundaries, and extending a run while the next chapter also occupies
the next position in BLB. The BLB PDF was parsed into all 365 readings and checked
for 1189 distinct chapters, matching the TSV inventory. The supplied Opus BLB
text was checked against the same numbered readings; the PDF SHA is above.
This table lists **every multi-book identical run of at least eight chapters**;
within-book canonical runs are also common and are not evidence of independent
ordering. No comparison with ESV/Reese is claimed.

| Identical chapter run | Chapters | BLB readings |
| --- | --- | --- |
| EXO 1–40 → LEV 1–27 → NUM 1–36 → DEU 1–32 | 135 | 30–81 |
| ACT 19 → 1CO 1–16 → 2CO 1–13 → ROM 1–16 → ACT 20–28 | 55 | 332–348 |
| JOS 1–24 → JDG 1–21 → RUT 1–4 | 49 | 82–97 |
| ZEC 9–14 → EST 1–10 → EZR 7–10 → NEH 1–11 | 31 | 264–272 |
| 2KI 17 → ISA 13–27 | 16 | 196–199 |
| JHN 20–21 → ACT 1–12 | 14 | 319–324 |
| PHP 1–4 → 1TI 1–6 → TIT 1–3 | 13 | 351–353 |
| 1KI 12–14 → 2CH 10–12 → 1KI 15 → 2CH 13–16 → 1KI 16 | 12 | 174–177 |
| ISA 9–12 → MIC 1–7 | 11 | 194–195 |
| HAG 1–2 → ZEC 1–8 | 10 | 262–264 |
| ZEP 1–3 → JER 1–6 | 9 | 218–220 |
| LUK 12–17 → JHN 11 → LUK 18 → MAT 19 | 9 | 299–304 |
| MAT 26 → MRK 14 → LUK 22 → JHN 13–17 | 8 | 313–315 |
| 1TH 1–5 → 2TH 1–3 | 8 | 331–331 |

The longest overall match is EXO 1–40 → LEV 1–27 → NUM 1–36 → DEU 1–32
(**135 chapters**), the shared historical backbone. The 55-chapter Pauline/Acts
run is retained because the corrected Romans travel anchor supports it.
Persian-era and kings/Chronicles runs likewise retain ruler/narrative order.
The remaining short Gospel/letter runs retain event phases or the conventional
letter grouping; moving them simply to change a metric would add no historical
support. The former complete BLB passion/resurrection run and 68-chapter late
letter run no longer survive.

`segments` are traversed in array order and expanded inclusively from `first`
to `last`. `supported_by` lists only sources verified for the **specific anchor/context
in `support_basis`**, not merely for belonging to the same era. It does not
claim identical boundaries or immediate neighbors. Empty support means an
editorial placement without a verified matching source anchor; all undated
anthology blocks have empty support and `placement_kind: undated-anthology`.
`era` is a reader-facing context, not a date of composition; anthology blocks
and chapter flashbacks can cross its boundaries. Each `decision_id` resolves
to exactly one table row. Confidence describes the historical association,
not software correctness: **high** = explicit narrative link; **medium** =
well-supported broad context; **low** = disputed date or convenience boundary.
The schedule generator must later keep each `same_day_pairs` entry indivisible.
Adjacency now does not prove same-day allocation later.

## Disputed placements and chapter-boundary compromises

| ID | Passage | Our placement | Alternatives in compared sources | Rationale / biblical anchor | Confidence |
| --- | --- | --- | --- | --- | --- |
| D01 | JOB 1–42 | After GEN 50, before EXO; patriarchal-context interlude | BLB readings 4–15 / BTTB Jan 4–15: after GEN 11. NLT Jan 19–31: after the Genesis narrative. | NLT's broad context keeps Genesis continuous. Patriarch-like family worship (JOB 1:5) supports a contextual association, not a date before Abraham or a date of composition. No majority for our exact boundary. | Low |
| D02 | JDG 1–21; RUT 1–4 | JOS → JDG → RUT, preserving each narrative | All three put Ruth after Judges (NLT Apr 7–8). Within Judges, the appendices 17–21 recount an earlier setting rather than events after Samson; the schemes retain the book's order. | RUT 1:1 explicitly places its story during the judges. Whole chapters do not establish a precise order of the overlapping judges; keep the narratives readable. | High for era; low for internal sequence |
| D03 | PSA 90 | Between DEU 32 and 33 | BLB reading 81: after DEU 34; BTTB Mar 1: after NUM 14–15; NLT Mar 21: after DEU 32, before 33–34. | The superscription associates the prayer with Moses. Choose NLT's farewell context beside the song of Moses; no claim that the Psalm was composed on that occasion. | Medium |
| D04 | 1CH 1–9 | 1CH 1–8 before Samuel; 1CH 9 immediately after NEH 11, before NEH 12–13 | BLB/BTTB put the genealogies after 2SA 1–4. NLT distributes genealogy verses through history and reads 1CH 9:1–34 beside NEH 11–12 (Sep 21). | 1CH 9:2–34 and NEH 11:3–19 concern the returned Jerusalem community. Its concluding Saul genealogy is the smaller declared flashback; chapters 1–8 remain an undated introductory dossier. | High for 9; low for introductory 1–8 |
| D05 | 1CH 10–29; 2CH 1–36 and Samuel/Kings | Parallel narrative blocks; 1CH 10 after 1SA 31; succession: 1KI 1 → 1CH 23–29 → anthology I–II → 1KI 2–4; 2CH 36 after 2KI 25 | BLB puts 1CH 10 with genealogies; BTTB/NLT beside Saul’s death. BLB/BTTB finish 1CH 23–29 before 1KI 1; NLT integrates the succession and Chronicles material at verse level. | 1CH 23:1 summarizes Solomon’s succession. Read 1KI 1 before the closing David dossier so his death in 1CH 29 does not precede his living appearance in 1KI 1. Larger whole chapters still overlap; 2CH 36 anticipates Cyrus. | High for parallels; medium for whole-chapter boundaries |
| D06 | Anchored PSA 3, 18, 30, 32, 34, 51, 52, 54, 56, 57, 59, 60, 63, 96, 105, 132, 142 | 34/56 after 1SA 21; 52 after 22; 54 after 23; 57/142 after 22 (Adullam); 96/105 after 1CH 16; 51/32 after repentance; 3/63 after 2SA 15; 18 after 2SA 22; 132 after temple dedication | BLB/BTTB put 56 in pursuit groups and 63 after 1SA 25–27; NLT puts 56 later near 1SA 27–29, but 3/63 together in Absalom’s rebellion. BLB/BTTB place 96/105 after the ark account; NLT’s complete Psalms appear in July. None places complete 132 at the temple dedication. | Psalm titles anchor the pursuit/repentance episodes; 2SA 22 parallels 18. 1CH 16 quotes 96/105 and parts of 106; 2CH 6:41–42 quotes 132:8–10. 63’s wilderness title and reference to a king support the Absalom context without proving it. 30/32 remain weaker thematic links. | High for named episodes/quotations; medium for 63; low for 30/32 |
| D07 | Undated Psalter Books I–V; PSA 74/79/126/137 | Unallocated 1–72 after David’s closing dossier; 73–89 beside LAM, including 74/79; 137 follows that block; unallocated 90–150 after NEH 13, including 126 | BLB/BTTB/NLT distribute or collect most Psalms in David/Solomon contexts, with differing exile/return associations. No compared plan uses our three complete anthology contexts. BLB/BTTB place 74/79 near the fall, 137 near EZR 4–6 and 126 after NEH; NLT’s complete 126 is in July. | Use the Psalter’s five-book structure (boundaries at 41/42, 72/73, 89/90, 106/107; PSA 72:20 closes the prayers of David). These are explicitly undated anthology contexts, not composition dates. Book III’s lament fits beside LAM; Books IV–V serve as restoration reading. Keep 9+10 and 114+115 adjacent. | Low for dates; high for anthology structure |
| D08 | PRO 1–24; SNG; ECC; PSA 72/127 | PRO 1–24/SNG after 1KI 4; 72/127 after temple accounts; ECC after 1KI 11 | BLB: SNG before PRO, ECC before 1KI 10–11; BTTB similar; both place PSA 127 with 1CH 26–29 before Solomon. NLT: PRO then SNG, ECC after 1KI 11; 72/127 after its Solomon narrative on May 26. | Use traditional Solomon associations (PRO 1:1, SNG 1:1, ECC 1:1, Psalm titles) for reading context. Temple songs and later reflection are editorial associations, not established composition dates or a claim that every proverb is Solomon's. | Low/medium |
| D09 | PRO 25–31 | After 2KI 18–20 / 2CH 29–32, before ISA 36–39 → 40–66 | BLB/BTTB retain 25–29 near Solomon, 30–31 at the end of his reign. NLT Jul 2–3 places 25–31 in the Hezekiah context before the Isaiah siege readings. | PRO 25:1 names Hezekiah’s copyists. Moving the collection before ISA 36 preserves ISA 39:6–7 → 40:1 as a continuous literary transition. Keeping 30–31 with it does not date Agur/Lemuel. | High for 25–29 collection; low for 30–31 |
| D10 | JON; AMO; HOS; MIC | JON/AMO after 2KI 14; HOS after 2KI 15 / 2CH 26–27; MIC after Ahaz’s 2KI 16 / 2CH 28 and ISA 7–12, before 2KI 17 | BLB/BTTB place Micah near Jotham; NLT splits MIC 1 before Ahaz and 6–7 amid Hezekiah. None verifies our exact whole-book boundary; MIC has empty source support. | Regnal headings establish overlapping ministries. JER 26:18 dates MIC 3:12 to Hezekiah; moving the whole book after Ahaz reduces premature reading of this oracle, although our boundary still anticipates the full Hezekiah account. | Medium for reigns; low for MIC whole-book boundary |
| D11 | ISA 1–66 | 1–6 near Uzziah/Jotham; 7–12 after Ahaz; 13–35 after 2KI 17; PRO precedes 36–39 → 40–66 in the Hezekiah context | BLB/BTTB put 7–8 earlier among Uzziah-period readings and 9–12 near Jotham; NLT Jun 23–25 puts 7–12 with Ahaz. All three read 40–66 in the Hezekiah-era reading context; composition-context ordering could instead place it near exile/return. | ISA 7:1 explicitly names Ahaz, 36:1 Hezekiah. Retain the continuous 39–40 transition. 40–66 anticipates exile/return; the plan does not decide authorship or assign a composition date to every oracle. | High for ISA 7 and 36 anchors; medium for sections; low for 40–66 |
| D12 | NAM; ZEP; HAB | NAM after Manasseh; ZEP after 2KI 22 / 2CH 34, before Josiah’s final narrative; HAB after 2KI 23 / 2CH 35, before collapse | BLB/BTTB put Zephaniah after the combined Josiah/final narrative and Habakkuk after the fall; NLT places Habakkuk before the last kings. Our ZEP boundary is grounded in its heading, not claimed as an exact source match. | ZEP 1:1 names Josiah; moving it before his death keeps the regnal context explicit. NAM recalls Thebes’ fall; HAB announces the Chaldean threat without naming an exact year. | High for ZEP reign; medium for broad NAM/HAB contexts |
| D13 | JER 1–52 | 1–6 during Josiah; 7–20, 22–23, 25–26 and 35–36/45 afterward; JER 24 after 2KI 24; then 27–31 and siege dossier 21/32–34/37–39; after fall 52, 40–44, 46–51 | BLB/BTTB largely keep chapter order. NLT moves dated pieces: 36/45 under Jehoiakim, 23:33–24:10 after Jehoiachin’s deportation, 21/32–34 amid the siege. Exact large-block grouping remains ours. | JER 1:2 and 3:6 name Josiah; JER 24:1 explicitly follows the 597 BCE deportation. This corrects the reviewed reversal. Jehoiakim and Zedekiah headings anchor their dossiers; 46–51 remains a retrospective, multi-date oracle collection. | High for JER 24/regnal anchors; medium for grouping |
| D14 | EZK; DAN; LAM | DAN 1–3 before the 597 deportation in 2KI 24; EZK 1–24 before fall; LAM after fall; EZK 25–48 → DAN 4 → 7–8 → 5–6 → 9 → EZR 1–3 → DAN 10–12 | BLB/BTTB read all Ezekiel after LAM and Daniel in chapter order. NLT reads Daniel 1–3 in the Jehoiakim setting, early Ezekiel before fall, 7–8 before 5, and 10–12 after early Ezra (Sep 10). | DAN 1:1 / 2:1 concern the earlier Jehoiakim/Nebuchadnezzar setting, not Jehoiachin’s 597 deportation. DAN 10:1 names Cyrus’s third year, so it follows EZR 1:1 (first year). EZK 1/24 and DAN 7/8 provide further explicit anchors; larger blocks retain some overlapping dates. | High for dated corrections; medium for large blocks |
| D15 | OBA | After Jerusalem's destruction and LAM, before later exile visions | BLB/BTTB place Obadiah near Jehoram, after 2CH 19–23. NLT Aug 28 puts it after Lamentations. | OBA 10–14 describes Edom's involvement in Jerusalem's disaster; a Babylonian-fall setting is plausible. An earlier raid is possible; the text gives no regnal heading. | Low |
| D16 | JOL | Restoration-era interlude after NEH and Psalms, before MAL | BLB/BTTB: after EZK, before DAN. NLT Sep 23: after MAL, just before the Gospels. Earlier pre-exilic dates are scholarly alternatives, not placements verified in these three PDFs. | No king or explicit date. Temple/community language permits several settings. Choose a late restoration context close to NLT, while leaving MAL as the final prophetic bridge; exact boundary is our own. | Low |
| D17 | EZR; HAG; ZEC; EST; NEH; MAL | EZR 1–3 → DAN 10–12 → EZR 4 → HAG → ZEC 1–8 → EZR 5–6 → ZEC 9–14 → EST → EZR 7–10 → NEH 1–11 → 1CH 9 → NEH 12–13 → anthology IV–V → JOL → MAL | BLB/BTTB complete EZR 1–6 before the prophets; NLT interleaves construction and prophecy and reads DAN 10–12 after early Ezra. All put EST between early return and EZR 7/NEH; NLT puts JOL after MAL. | Cyrus’s first/third years determine the new Daniel insertion. EZR 5:1 names Haggai/Zechariah; ruler sequence orders Esther/Ezra/Nehemiah. EZR 4:6–23 remains a whole-chapter flash-forward; MAL 3–4 stays indivisible. | High for ruler/construction sequence; low for ZEC 9–14/MAL dates |
| D18 | Infancy, baptism and early Judean ministry | LUK 1–2 → MAT 1–2 → MAT 3 → LUK 3 → JHN 1–4 → main Galilean block | BLB/BTTB place the opening John material among infancy and read JHN 2–4 after the initial Galilean chapters. NLT/R interleave John’s early Judean episodes before the post-arrest Galilean phase. | JHN 3:24 precedes John’s imprisonment; MAT 4:12 / MRK 1:14 follow it. JHN 1’s adult testimony follows the baptism accounts. Whole MRK 1/MAT 4/LUK 4 still begin with baptism/temptation flashbacks; John’s prologue is not dated to that moment. | High for pre/post-arrest phases; medium for whole chapters |
| D19 | Galilean chapter harmony | JHN 5 before MRK 2–3 and preaching blocks; feeding cluster MAT 14/MRK 6/JHN 6; LUK 9 after MRK 9, before MAT 18 | BLB puts JHN 5 before MAT 12/MRK 3, but after MRK 2. NLT/R place JHN 5 before the Sabbath disputes (which occupy the end of MRK 2) while earlier MRK 2 episodes precede it. BLB reads complete LUK 9 with the feeding; BTTB/NLT divide it. | Moving all JHN 5 before MRK 2–3 preserves the Sabbath/discourse phase, with an acknowledged flashback to MRK 2’s earlier miracles. LUK 9 after MRK 9 aligns confession/transfiguration/travel onset; its feeding account becomes the smaller flashback. MAT 5–7 remains intact. | Medium for event clusters; low for exact whole-chapter order |
| D20 | LUK 10–18; JHN 7–11; MAT 19–20; MRK 10 | JHN 7–10 → LUK 10–17 → JHN 11 → LUK 18 → MAT 19–20/MRK 10 | BLB/BTTB split Luke's journey around John; NLT/R Parts IX–X interleave Judean/Perean episodes at verse level. | Luke's long journey collection stays readable; John's festivals and Lazarus retain their order. LUK 18 contains Jericho, also treated in LUK 19; thematic collections do not permit an exact chapter chronology. | Low/medium |
| D21 | Final week and resurrection | Entry/disputes/discourses; MAT 26 → MRK 14 → LUK 22 → JHN 13–17; JHN 18–19 before Synoptic crucifixion chapters; resurrection MAT 28 → LUK 24 → MRK 16 → JHN 20–21 | BLB’s MAT 26 → MRK 14 → LUK 22 → JHN 13–17 run is retained; its trial/crucifixion and resurrection account order differs. NLT/R interleave these episodes by verses. | All three and R agree on phases. John’s trial/crucifixion as the first complete account and Luke’s resurrection account before Mark are equally defensible parallel-account readings. This breaks the former 22-chapter BLB passion/resurrection run without implying precise within-phase chronology. | High for phases; medium for account order |
| D22 | JAS; GAL | JAS after ACT 12; GAL after ACT 14, before council in ACT 15 | BLB/BTTB: JAS after ACT 14, GAL after ACT 16. NLT: GAL after ACT 14, JAS after prison letters in December. | Early Jerusalem James is a traditional contextual choice; ACT 12:17 is a convenient introduction, not proof of authorship/date. GAL uses the southern-Galatia/pre-council hypothesis; northern/later dating remains possible. No consensus on these exact positions. | Low |
| D23 | ACT 15–28; 1/2TH; 1/2CO; ROM | ACT 15–18 → 1TH/2TH → ACT 19 → 1CO → 2CO → ROM → ACT 20–28 | BLB matches ACT 19 → 1CO → 2CO → ROM → ACT 20–28; BTTB inserts ACT 20:1–3 before ROM; NLT puts ROM before 2CO after ACT 19:21–20:6. | ROM 15:25–26 anticipates Jerusalem travel. Move it before the whole ACT 20 account of departure from Greece and onward travel. Letters anticipate movements summarized in ACT 20:1–3; chronology takes precedence over reducing source similarity. | Medium |
| D24 | Prison, pastoral and other late letters | EPH → COL → PHM → PHP → 1TI → TIT → 2TI → HEB → 1PE → 2PE → 1JN → 2JN → 3JN → JUD | BLB/BTTB have COL/PHM before EPH and 1PE/HEB before 2TI, with JUD before John. NLT has EPH before COL/PHM, 2TI before HEB/1PE, and JUD after John. | Use NLT’s equally defensible ordering for undated/contested late letters instead of the former 68-chapter BLB run. Keep COL/PHM together through shared names; traditional post-Acts prison/pastoral context is approximate. HEB is not assigned to Paul. | Low |
| D25 | REV 1–22 | Final book, after Johannine letters | All three put Revelation last. An early/Neronian date would change the position among late letters; this alternative is not followed in the compared schedules. | Follow common traditional late-apostolic placement and the book's own narrative order. Its visions are not a dated event sequence; no prediction timeline is inferred from placement. | Medium for conventional placement; low for exact date |

## Verification and review boundary

Run `.venv/bin/python tools/validate_chronological_sequence.py`. It checks the
source TSV inventory, valid USFM IDs, inclusive non-reversed integer ranges,
1189 chapters exactly once across 66 books, all three adjacency constraints,
and source/era/decision references. Targeted negative tests live in
`tests/test_chronological_sequence.py`. These checks verify structure, not
historical judgments. Two independent editorial reviews of 9baff89 were incorporated in this revision.
Owner approval of the revised table remains required before publication; no calendar or marker is implemented
in this data-only step.


## Response to the two editorial reviews

All mandatory corrections and the single-reviewer recommendations were accepted:
Josiah/Ahaz/Micah contexts, David’s succession, John 5, Luke 9, Proverbs before
Isaiah 36, and all named dated placements. The only optional suggestions not
used as event placements are PSA 7 (Cush cannot be identified securely) and the
complete PSA 106 beside 1CH 16. Psalm 106 quotes there only in part; its plea for
gathering from the nations fits its retained, explicitly undated Book IV block.
No date is inferred from that choice. This is not a rejection of the quotation.

Changed decision rows: D04–D07, D09–D14, D17–D19, D21, D23–D24.
Unchanged choices (including Job and disputed minor-prophet dates) remain
explicitly low-confidence where appropriate.

Verification after revision on 2026-10-04:
`.venv/bin/python tools/validate_chronological_sequence.py` exited **0**:
248 segments, 1189 unique chapters, 66 books and all three required pairs adjacent.
`.venv/bin/python -m unittest discover -s tests -p test_chronological_sequence.py`
exited **0** (8 tests, including dated review anchors and malformed inputs).
The longest uninterrupted single-book stretch is **58 chapters of PSA**,
the undated Books I–II anthology (remaining chapters from PSA 1–72).
The undated Book III block has 17 chapters; remaining Books IV–V have 54.
These counts describe reading context, not composition chronology.
