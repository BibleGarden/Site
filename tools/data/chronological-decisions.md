# Bible Garden chronological sequence: editorial decisions (version 1)

Status: draft for owner and independent editorial review. Source comparison and
chapter checks dated **2026-10-04**. References use Hebrew/BSB chapter numbers and
USFM book codes, including four chapters in MAL. This is a reading order of
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
Explicit biblical headings and narrative connections settle the finer choices;
when schemes disagree, the table below makes the editorial choice explicit.
Consecutive chapters are grouped by our own narrative boundaries. No publisher's
365-day allocation, headings, commentary or complete ordering was imported.
BLB/BTTB's speculative placement of nearly every Psalm is deliberately avoided;
NLT's genealogy fragments and verse harmony are not reproduced.

`segments` are traversed in array order and expanded inclusively from `first`
to `last`. `supported_by` means **broad historical context only**, not exact
endpoints or immediate neighbors. Empty support means our editorial placement.
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
| D04 | 1CH 1–9 | One genealogy block before 1SA 1, introducing monarchy | BLB readings 113–120 / BTTB Apr 23–29: after 2SA 1–4, interleaved with Psalms. NLT scatters genealogy verses from Genesis through the return (including 1CH 9 in September). | These chapters span Adam to returned inhabitants (1CH 9:1–2); a whole-chapter chronology cannot distribute them accurately. Our introductory dossier is a declared exception, not consensus or an early date for its final form. | Low |
| D05 | 1CH 10–29; 2CH 1–36 and Samuel/Kings | Parallel chapters after the corresponding narrative block; 1CH 10 after Saul's death; 2CH 36 after 2KI 25 | BLB and BTTB alternate many short blocks, but BLB places 1CH 10 with genealogies, BTTB with 1SA 31 and again in its genealogy range. NLT interleaves verses, e.g. 2CH 36:22–23 only at the return. | 1CH 10/1SA 31, 1CH 17/2SA 7 and 2CH 36/2KI 24–25 identify the parallels. Our own larger blocks preserve every chapter once. 2CH 36 necessarily anticipates Cyrus; 2CH 32 includes events extending beyond the siege. | High for parallels; medium for boundaries |
| D06 | PSA 3, 18, 30, 32, 34, 51, 52, 54, 57, 59, 60, 142 | Explicit-context Psalms follow Saul's pursuit, David's wars, repentance or flight; PSA 18 after 2SA 22; 30 after census/altar account | All three connect several titled Psalms with David, but BLB/BTTB group more loosely: PSA 18 after 1SA 31; PSA 57 after 2SA 22–23. NLT puts 18 beside 2SA 22 and 57/142 in the cave episode. | Superscriptions anchor 3, 34, 51, 52, 54, 57, 59, 60, 142; 2SA 22 parallels 18. PSA 32 accompanies 51 thematically; PSA 30's dedication title does not identify a unique event. These two are explicit low-confidence associations. | High/medium for titled context; low for 30/32 |
| D07 | Remaining PSA; especially 74, 79, 126, 137 | 74/79/137 after LAM; 126 after NEH; all remaining unallocated Psalms in canonical order after that | BLB/BTTB distribute almost all Psalms across David/Solomon; 74/79 at Jerusalem's fall, 137 beside EZR 4–6, 126 after NEH. NLT places many undated Psalms in May–July, 126 among July Psalms and 137 with exile genealogies. | 137 names Babylon; 74/79 describe sanctuary devastation but its exact occasion is debated; 126 evokes restoration without naming a ruler. The final anthology is a reading-context exception, not a claim that all remaining Psalms are post-exilic. Keep 9+10 and 114+115 adjacent. | Medium for 137; low for other dates |
| D08 | PRO 1–24; SNG; ECC; PSA 72/127 | PRO 1–24/SNG after 1KI 4; 72/127 after temple accounts; ECC after 1KI 11 | BLB: SNG before PRO, ECC before 1KI 10–11; BTTB similar; both place PSA 127 with 1CH 26–29 before Solomon. NLT: PRO then SNG, ECC after 1KI 11; 72/127 after its Solomon narrative on May 26. | Use traditional Solomon associations (PRO 1:1, SNG 1:1, ECC 1:1, Psalm titles) for reading context. Temple songs and later reflection are editorial associations, not established composition dates or a claim that every proverb is Solomon's. | Low/medium |
| D09 | PRO 25–31 | After Hezekiah's narrative (2KI 18–20; 2CH 29–32) | BLB/BTTB keep 25–29 near Solomon, 30–31 after his reign. NLT Jul 2–3 puts 25–31 within the Hezekiah period. | PRO 25:1 expressly names Hezekiah's copyists. Keep 30–31 with the final collection for continuity; Agur and Lemuel are not thereby dated to Hezekiah. | High for 25–29 collection; low for 30–31 |
| D10 | JON; AMO; HOS; MIC | JON/AMO after 2KI 14; HOS/MIC after 2KI 15 and 2CH 26–27 | BLB/BTTB: Jonah after 2KI 14, Amos later among Isaiah, Hosea after initial Hezekiah narrative; Micah near Jotham. NLT Jun 20–27: Jonah/Amos then Micah and Hosea amid eighth-century reigns. | 2KI 14:25 names Jonah; AMO 1:1, HOS 1:1, MIC 1:1 identify reigns. Books cover overlapping reigns; whole-book blocks are contexts, not exact dates for every oracle. | Medium |
| D11 | ISA 1–66 | 1–12 near Uzziah/Jotham; 13–35 near Ahaz; 36–39 beside Hezekiah parallels; 40–66 after Hezekiah, before later Judah | BLB/BTTB split Isaiah repeatedly through these reigns; NLT rearranges some chapters (6 before 1–5), but also reads 40–66 in July beside Hezekiah. An alternative composition-context reading would put 40–66 with exile/return; it is not the compared schedules' placement. | ISA 1:1 and 36:1 anchor the narrative context; 40–66 anticipates exile and restoration. Preserve broad section order without resolving the authorship/composition debate. This records the schemes' traditional context, not a date assigned to every oracle. | Medium for 1–39; low for 40–66 |
| D12 | NAM; ZEP; HAB | NAM after Manasseh; ZEP/HAB after Josiah's narrative, before final collapse | BLB/BTTB put Nahum after 2CH 33 and Zephaniah after Josiah, but Habakkuk after the fall readings. NLT Aug 1–3 places Nahum/Habakkuk/Zephaniah before the last kings. | NAM 3:8–10 recalls Thebes' fall; ZEP 1:1 names Josiah; HAB 1:6 announces the Chaldean threat. Habakkuk before the collapse makes that warning legible, without pretending to know a precise year. | Medium; low for HAB's exact date |
| D13 | JER 1–52 | Early ministry 1–20, 22–26; Jehoiakim dossier 35–36/45; then 27–31; Zedekiah dossier 21/32–34/37–39; after fall: 52, 40–44, 46–51 | BLB/BTTB largely retain chapter order across the fall. NLT moves dated chapters and splits oracles by verses (e.g. 36/45 in Jehoiakim, 21/32–34 during siege). | JER 35:1, 36:1, 45:1 share Jehoiakim context; 21:1, 32:1, 34:1 and 37:1 anchor Zedekiah. Appendix 52 retells the fall. Multi-date foreign-nation oracles 46–51 stay together as a retrospective dossier; predictions and chapter flashbacks remain. | Medium |
| D14 | EZK; DAN; LAM | DAN 1–3 after first deportation; EZK 1–24 before fall; LAM after fall; EZK 25–48 then DAN 4 → 7–8 → 5–6 → 9–12 | BLB/BTTB read all Ezekiel after the fall and Daniel 1–12 in book order. NLT places early Ezekiel before the fall, DAN 1–3 earlier, 7–8 before 5, and 9 near 6; many dated pieces interleaved. | EZK 1:1–2 and 24:1–2 bracket exile/siege. DAN 7:1 and 8:1 precede Belshazzar's fall in 5; 9–12 span Darius/Cyrus. Larger blocks avoid verse fragments, but EZK 25–48 contains dates on both sides of the fall and DAN 4's exact date is uncertain. | Medium; high for DAN 7–8 before 5 |
| D15 | OBA | After Jerusalem's destruction and LAM, before later exile visions | BLB/BTTB place Obadiah near Jehoram, after 2CH 19–23. NLT Aug 28 puts it after Lamentations. | OBA 10–14 describes Edom's involvement in Jerusalem's disaster; a Babylonian-fall setting is plausible. An earlier raid is possible; the text gives no regnal heading. | Low |
| D16 | JOL | Restoration-era interlude after NEH and Psalms, before MAL | BLB/BTTB: after EZK, before DAN. NLT Sep 23: after MAL, just before the Gospels. Earlier pre-exilic dates are scholarly alternatives, not placements verified in these three PDFs. | No king or explicit date. Temple/community language permits several settings. Choose a late restoration context close to NLT, while leaving MAL as the final prophetic bridge; exact boundary is our own. | Low |
| D17 | EZR; HAG; ZEC; EST; NEH; MAL | EZR 1–4 → HAG → ZEC 1–8 → EZR 5–6 → ZEC 9–14 → EST → EZR 7–10 → NEH → concluding MAL | BLB/BTTB finish EZR 1–6 before HAG/ZEC; NLT interleaves HAG/ZEC with the resumed construction. All place EST between early return and EZR 7/NEH, and MAL after NEH; NLT adds JOL after MAL. | EZR 5:1 names the two prophets; HAG 1:1 and ZEC 1:1 date them under Darius; ZEC 9–14 lacks those dates. EST 1:1 / EZR 7:1 / NEH 2:1 supply ruler sequence (traditional Xerxes identification). EZR 4:6–23 is an unavoidable later-period flash-forward. MAL 3–4 must be indivisible for UK. | High for named rulers/construction; low for ZEC 9–14/MAL date |
| D18 | LUK 1–3; MAT 1–3; JHN 1; MRK 1 | LUK 1–2 → MAT 1–2 → JHN 1, then baptism/opening-ministry chapters | BLB begins LUK 1/JHN 1, then MAT 1/LUK 2. BTTB splits JHN 1 and LUK 2. NLT interleaves birth/genealogy verses; R Parts II–V separates pre-existence, genealogies, infancy and baptism. | Whole JHN 1 includes both prologue and adult ministry, MAT 1 combines genealogy/birth and LUK 3 genealogy/baptism. Place the earliest complete infancy account first; resulting overlaps are declared, not a strict verse harmony. | Medium for phases; low for chapter boundary |
| D19 | Galilean chapters MAT 4–18; MRK 1–9; LUK 4–9; JHN 2–6 | Own chapter blocks, grouping preaching, miracles, feeding, confession and transfiguration | BLB puts MAT 8 before 5–7 and MAT 10 after MRK 4–5. NLT/BTTB split chapters to align episodes. R Parts VI–VIII align pericopes, not complete chapters. | Keep MAT 5–7 intact before its miracle collection and MAT 10–12 together; align MAT 14/MRK 6/LUK 9/JHN 6 and MAT 16–17/MRK 8–9 broadly. LUK 9 also anticipates travel. The order is a chapter-level approximation; it cannot date all teaching collections. | Medium for episode clusters; low for full-chapter order |
| D20 | LUK 10–18; JHN 7–11; MAT 19–20; MRK 10 | JHN 7–10 → LUK 10–17 → JHN 11 → LUK 18 → MAT 19–20/MRK 10 | BLB/BTTB split Luke's journey around John; NLT/R Parts IX–X interleave Judean/Perean episodes at verse level. | Luke's long journey collection stays readable; John's festivals and Lazarus retain their order. LUK 18 contains Jericho, also treated in LUK 19; thematic collections do not permit an exact chapter chronology. | Low/medium |
| D21 | Final-week and resurrection chapters | Entry cluster, disputes, eschatological discourse, supper, trials/crucifixion, resurrection; each account's whole chapter once | All three and R Parts XI–XIV share those phases; they differ in interleaving, e.g. BLB reads MAT 20–21 before LUK 19 and NLT splits last-supper/trial chapters. | Explicit narrative milestones justify phase agreement. Whole chapters straddle phases (LUK 21, MAT 26, JHN 18–19); sequence does not harmonize Passover dating or every resurrection appearance. | High for phases; medium for boundaries |
| D22 | JAS; GAL | JAS after ACT 12; GAL after ACT 14, before council in ACT 15 | BLB/BTTB: JAS after ACT 14, GAL after ACT 16. NLT: GAL after ACT 14, JAS after prison letters in December. | Early Jerusalem James is a traditional contextual choice; ACT 12:17 is a convenient introduction, not proof of authorship/date. GAL uses the southern-Galatia/pre-council hypothesis; northern/later dating remains possible. No consensus on these exact positions. | Low |
| D23 | ACT 15–28; 1/2TH; 1/2CO; ROM | ACT 15–18 → Thessalonian letters → ACT 19 → 1CO → 2CO → ACT 20 → ROM → ACT 21–28 | BLB puts 1/2TH after ACT 17 (before Corinth in 18) and ROM before ACT 20. BTTB splits ACT 18/20; NLT places Thessalonians within ACT 18 and ROM before 2CO after ACT 19:21–20:6. | ACT 18 supplies Corinth context for Thessalonians; 1CO 16:8 names Ephesus; 2CO 2:12–13 / 7:5 Macedonia; ROM 15:25–26 the coming Jerusalem visit. Put 2CO before ROM as the conventional travel reconstruction. Whole ACT 20 includes the travel onward and hence anticipates part of the next phase. | Medium |
| D24 | EPH/COL/PHM/PHP; pastorals; HEB; Peter/Jude/John | After ACT 28: EPH → COL → PHM → PHP → 1TI → TIT → 1PE → HEB → 2TI → 2PE/JUD → Johannine letters | BLB/BTTB: COL/PHM before EPH; NLT: EPH before COL/PHM. BLB/BTTB put 1PE/HEB before 2TI; NLT puts 2TI before HEB/1PE and JUD after John. | Traditional Roman-prison context keeps PHM beside COL (shared names), with pastorals after Acts. Exact dating/authorship of these letters and alternative imprisonments are contested; HEB is not assigned to Paul. Final letter grouping is an editorial reading context, not demonstrated composition order. | Low |
| D25 | REV 1–22 | Final book, after Johannine letters | All three put Revelation last. An early/Neronian date would change the position among late letters; this alternative is not followed in the compared schedules. | Follow common traditional late-apostolic placement and the book's own narrative order. Its visions are not a dated event sequence; no prediction timeline is inferred from placement. | Medium for conventional placement; low for exact date |

## Verification and review boundary

Run `.venv/bin/python tools/validate_chronological_sequence.py`. It checks the
source TSV inventory, valid USFM IDs, inclusive non-reversed integer ranges,
1189 chapters exactly once across 66 books, all three adjacency constraints,
and source/era/decision references. Targeted negative tests live in
`tests/test_chronological_sequence.py`. These checks verify structure, not
historical judgments. Owner approval of the table and independent editorial
review remain required before publication; no calendar or marker is implemented
in this data-only step.

Validation recorded on 2026-10-04: the command above exited 0 for 231 segments,
1189 unique chapters and 66 books.
`.venv/bin/python -m unittest discover -s tests -p test_chronological_sequence.py`
also exited 0 (5 tests, including deliberate malformed-sequence cases).
