# Detector B: Claude's verdicts on its 30 unmatched flags (S12-R1 sitting, 2026-10-12)

Input: `probe_unmatched_B.log` (`uv run python eval/results/s12-sitting/probe_unmatched.py B`). Chunk windows checked against conflict run 1's hits.

**Rule applied** (S10-T8's precedents):
- **Real:** the two chunks, as shown to the model, state incompatible facts about the same thing at the question's target release. That includes an older and a newer version of one text whose meaning changed (S10: q34 9930 vs. 9931, Real).
- **Not real:**
  - A claim line from a KEP version that isn't valid at the target, compared with a later state. ADR-010 D1 takes a KEP's claim from its newest version valid at the target; S10 called "an old version claims alpha, observed stable" false (q44, q45).
  - A gate removed after GA, set against "stable".
  - Design text describing a graduation path.
  - Links or cosmetic edits.

| # | Question | Pair | Verdict | Why |
|---|---|---|---|---|
| U1 | q08 | 15239 vs. 10059 | Not real | KEP-2579 version valid to 1.24; target 1.37 |
| U2 | q08 | 15216 vs. 10059 | Not real | KEP-2579 version valid to 1.22 |
| U3 | q12 | 15818 vs. 16058 | Not real | KEP-2799 version valid to 1.26 vs. its current version: status progressed |
| U4 | q15 | 16060 vs. 9963 | Not real | Gate removed after GA is consistent with stable |
| U5 | q18 | 30877 vs. 10420 | Not real | KEP-4858 version valid 1.32–1.35 |
| U6 | q18 | 30877 vs. 31042 | Not real | The same old version vs. its later history |
| U7 | q19 | 30886 vs. 10420 | Not real | KEP-4858 version valid 1.32–1.35 |
| U8 | q30 | 16403 vs. 16386 | Not real | Design text on alpha/beta code paths, not a stage claim |
| U9 | q33 | 17974 vs. 17549 | Not real | Target 1.28: 17974's "stable" is from a version valid from 1.29 |
| U10 | q33 | 17974 vs. 17515 | Not real | As U9 |
| U11 | q34 | 9930 vs. 9931 | **Real** | KMSv2 gate page versions: stable with no end vs. ended 1.31 and removed (S10's verdict) |
| U12 | q34 | 9931 vs. 43083 | Not real | Gate removed after GA vs. "stable": consistent |
| U13 | q34 | 17132 vs. 9930 | Not real | KEP-3299 version valid to 1.28 |
| U14 | q34 | 17054 vs. 9930 | Not real | KEP-3299 version valid to 1.27 |
| U15 | q35 | 41925 vs. 42160 | **Real, borderline** | S10's verdict on the same pair |
| U16 | q35 | 10191 vs. 10192 | **Real** | ValidatingAdmissionPolicy gate page versions: the same pattern as U11 |
| U17 | q36 | 17600 vs. 45854 | Not real | KEP-3331 version valid to 1.29 |
| U18 | q36 | 17515 vs. 45854 | Not real | KEP-3331 version valid to 1.28 |
| U19 | q36 | 17552 vs. 45854 | Not real | KEP-3331 version valid to 1.29 |
| U20 | q36 | 18030 vs. 45854 | Not real | A latest milestone (v1.35) after GA (v1.34) isn't a GA date |
| U21 | q40 | 8951 vs. 31538 | Not real | KEP-5495 plans later stages, so "implementable" is right |
| U22 | q43 | 24597 vs. 1551 | Not real | "Stage unknown" claims no stage |
| U23 | q43 | 24598 vs. 1551 | Not real | As U22 |
| U24 | q44 | 29668 vs. 13783 | Not real | KEP-3866 version valid to 1.30 (S10's q44 precedent) |
| U25 | q45 | 24214 vs. 24402 | Not real | KEP-1880 version valid to 1.30 (S10's q45 precedent) |
| U26 | q45 | 24104 vs. 24402 | Not real | KEP-1880 version valid to 1.26 |
| U27 | q45 | 24071 vs. 24402 | Not real | KEP-1880 version valid to 1.26 |
| U28 | q45 | 24304 vs. 24402 | Not real | KEP-1880 version valid to 1.33 vs. current: status updated |
| U29 | q47 | 31504 vs. 31536 | Not real | KEP-5495 version valid to 1.36 vs. current: plan extended |
| U30 | c02 | 38717 vs. 38777 | Not real | A tutorial link changed |

**Result:** 3 of 30 real (U15 borderline).
- **Judged precision, all flags:** (57 + 3) / 87 = 0.690. Without U15: 59 / 87 = 0.678.
- **Judged precision, model flags only:** (49 + 3) / 79 = 0.658.
- **The spec's threshold is ≥ 0.90:** B fails it.
- **The pattern:** 19 of the 27 not-real flags (U1–U3, U5–U7, U9–U10, U13–U14, U17–U19, U24–U29) compare a claim line from a KEP version that isn't valid at the target with a later state. B's added line invites exactly that comparison.
