# EVALUATION — paper-repro-auditor

Status against the shared adoption bar (`ADOPTION_BAR.md`), measured 2026-11-03 on commit `main`.

| Bar item | Result |
|---|---|
| 1. Never crashes on messy input | **Met.** 43 robustness tests; 23 crashes found and fixed at the root (list below). |
| 2. Installs cleanly from GitHub on 3.9 / 3.12 / 3.13 | **Met.** `pip install git+https://github.com/Yenula-W/paper-repro-auditor` in fresh venvs on macOS system Python 3.9.6, python.org 3.9.7, 3.12.15 and 3.13.16; README quickstart copy-pasted verbatim on 3.9.7 and produced a report. |
| 3. Held-out real-world run, ≥20 inputs, zero crashes | **Met.** 48 papers never used in development, 10+ fields, live network, final code: **0 crashes**, median 2.0 s, max 18.2 s, 163 s total, median output 8.2 KB (max 44 KB). |
| 4. Precision by hand, ≥90% overall, no check <80% | **Met on the last untouched round, not on the combined first runs.** Round 3 (untouched, first run): **91%**, lowest check 80%. All three rounds' first runs combined: 84% (code_statement 72%, links_alive 75%, code_link 78%). After root-cause fixes, every wrong judgment in all three rounds is fixed (360/360 correct or debatable), but that figure is measured on data that drove the fixes. Details below. |
| 5. Never invents or overstates | **Met, with wording changes.** Messages rewritten (see "Message review"); report header says FAIL = "not found or not verified automatically". Unverifiable links are never called dead. |
| 6. CI green, repo private | **Met.** GitHub Actions: Ubuntu 3.9 / 3.12 / 3.13, macOS 3.9 / 3.12 all green; `Yenula-W/paper-repro-auditor` is PRIVATE. |
| 7. EVALUATION.md committed and pushed | This file. |

## 1. Robustness (bar item 1)

`tests/test_robustness.py` (43 tests, no network) feeds the CLI and every parser messy input. **23 tests failed
on first run**; each was fixed at the root:

| Input | Crash before | Fix |
|---|---|---|
| empty / whitespace / free text / `10.` / `arXiv:` / web URL as input (6) | uncaught `ValueError` traceback | CLI catches, prints `error: …`, exit 2 |
| empty file, garbage, `%PDF` header + junk, UTF-16 text named `.pdf` (4) | `pypdf` `PdfStreamError` / `PdfReadError` | `safe_pdf_to_text`; report says "PDF could not be parsed", `full_text` FAIL |
| unicode path + broken PDF | same | same |
| unreadable file (chmod 000) | `PermissionError` | clean "permission denied" error |
| directory named `x.pdf` | `IsADirectoryError` | input classifier checks `is_file()` |
| symlink loop | `ValueError` traceback | clean error |
| 30 MB random "PDF" | `PdfStreamError` | safe parser |
| DOI with network unavailable | `OfflineError` traceback | clean error, exit 2 |
| UTF-16 batch CSV, binary batch CSV (2) | `UnicodeDecodeError` / `_csv.Error: line contains NUL` | BOM-aware decode, NULs stripped |
| missing batch CSV | `FileNotFoundError` | clean error |
| 5000-deep nested XML | `RecursionError` | falls back to flat text |
| Crossref `date-parts: [[null]]` | `TypeError` | null-safe date |
| Europe PMC returns unparsable XML | crash in fallback path | warning + continue |

Also covered and passing: BOM header CSV, blank/comment rows, symlink loops / broken links / unreadable
dirs / binary README / unicode file names inside a cloned repo, unwritable output directory,
pathological text for the extractors.

## 2. Install (bar item 2)

```
uv venv -p /usr/bin/python3 (3.9.6, macOS system)  + uv pip install git+https://github.com/Yenula-W/paper-repro-auditor  -> OK
uv venv -p 3.12 (3.12.15)                            + same                                                       -> OK
uv venv -p 3.13 (3.13.16)                            + same                                                       -> OK
python3 -m venv .venv && source .venv/bin/activate && pip install "git+…" && paper-audit 10.1371/journal.pone.0224321
   (python.org 3.9.7, README quickstart verbatim)    -> report written to audit-out/
```

Python 3.9 is supported (only deps: `requests`, `pypdf`). On macOS system Python, urllib3 2 warns about
LibreSSL; the warning is silenced, functionality is unaffected.

## 3. Held-out real-world run (bar item 3)

48 open-access papers that were **not** used during development (the 18 development papers in
`examples/handcheck.csv` / `examples/heldout.csv` are excluded), picked by Europe PMC / arXiv queries
designed to hit: no code, "available on request", dead links, Zenodo / OSF / Figshare / Dryad deposits,
old (2011–2016) papers, web-server papers, review articles. Fields: biology, cell biology, genomics,
bioinformatics, computational biology, microbiology, neuroscience, psychology, ecology, evolution,
medicine/epidemiology, chemistry, climate, geophysics, physics, astrophysics, computer science.

Final live run (no cache, final code, `GITHUB_TOKEN` set): **48/48 audited, 0 crashes, 0 errors**;
full text obtained for 48/48 (41 Europe PMC XML, 7 PDF). Runtime per paper: median 2.0 s, max
18.2 s (163 s total, including blobless clones of up to 2 repos per paper). Report size: median 8.2 KB, max 44 KB.

Rounds: **round 1** = papers 1–28, **round 2** = 29–38, **round 3** = 39–48. Each round was run once
with the code as it stood, hand-checked, then fixed; the next round was untouched by those fixes.

| # | Round | Paper | Field | Hand-checked | Score | Runtime (s) | Output (KB) |
|---|---|---|---|---|---|---|---|
| 1 | 1 | [10.1016/j.celrep.2019.09.064](https://doi.org/10.1016/j.celrep.2019.09.064) | biology | yes | 79 | 5.6 | 11.7 |
| 2 | 1 | [10.1074/jbc.ra118.004810](https://doi.org/10.1074/jbc.ra118.004810) | biology | yes | 62 | 1.1 | 3.4 |
| 3 | 1 | [10.1074/jbc.ra118.002779](https://doi.org/10.1074/jbc.ra118.002779) | biology |  | 50 | 1.7 | 3.8 |
| 4 | 1 | [10.1098/rsos.200793](https://doi.org/10.1098/rsos.200793) | psychology | yes | 100 | 2.4 | 8.5 |
| 5 | 1 | [10.1098/rsos.200664](https://doi.org/10.1098/rsos.200664) | psychology | yes | 100 | 0.7 | 8.5 |
| 6 | 1 | [10.3389/fpsyg.2021.775338](https://doi.org/10.3389/fpsyg.2021.775338) | psychology | yes | 50 | 0.7 | 6.8 |
| 7 | 1 | [10.3389/fpsyg.2021.712111](https://doi.org/10.3389/fpsyg.2021.712111) | psychology |  | 33 | 1.1 | 6.3 |
| 8 | 1 | [10.1002/ece3.9630](https://doi.org/10.1002/ece3.9630) | ecology | yes | 100 | 2.3 | 5.6 |
| 9 | 1 | [10.1002/ece3.9623](https://doi.org/10.1002/ece3.9623) | ecology | yes | 95 | 3.1 | 11.7 |
| 10 | 1 | [10.1371/journal.pone.0156543](https://doi.org/10.1371/journal.pone.0156543) | ecology/biology | yes | 57 | 1.5 | 21.6 |
| 11 | 1 | [10.1371/journal.pone.0168884](https://doi.org/10.1371/journal.pone.0168884) | ecology/biology |  | 100 | 1.3 | 6.3 |
| 12 | 1 | [10.1371/journal.pcbi.1002284](https://doi.org/10.1371/journal.pcbi.1002284) | computational biology | yes | 65 | 15.7 | 8.4 |
| 13 | 1 | [10.1371/journal.pcbi.1002147](https://doi.org/10.1371/journal.pcbi.1002147) | computational biology |  | 50 | 2.1 | 8.9 |
| 14 | 1 | [10.1093/nar/gku294](https://doi.org/10.1093/nar/gku294) | bioinformatics | yes | 57 | 5.6 | 4.5 |
| 15 | 1 | [10.1093/nar/gku460](https://doi.org/10.1093/nar/gku460) | bioinformatics |  | 36 | 1.2 | 4.5 |
| 16 | 1 | [10.1093/bioinformatics/btt500](https://doi.org/10.1093/bioinformatics/btt500) | bioinformatics |  | 70 | 0.8 | 5.7 |
| 17 | 1 | [10.1093/bioinformatics/btt094](https://doi.org/10.1093/bioinformatics/btt094) | bioinformatics |  | 33 | 0.6 | 3.5 |
| 18 | 1 | [10.1186/s12916-020-01863-9](https://doi.org/10.1186/s12916-020-01863-9) | medicine |  | 50 | 0.5 | 5.4 |
| 19 | 1 | [10.1186/s12916-020-01839-9](https://doi.org/10.1186/s12916-020-01839-9) | medicine | yes | 50 | 15.9 | 10.7 |
| 20 | 1 | [10.1523/eneuro.0202-21.2021](https://doi.org/10.1523/eneuro.0202-21.2021) | neuroscience | yes | 86 | 3.4 | 13.2 |
| 21 | 1 | [10.1371/journal.pbio.3000205](https://doi.org/10.1371/journal.pbio.3000205) | neuroscience |  | 71 | 1.5 | 6.9 |
| 22 | 1 | [10.1371/journal.pbio.3000479](https://doi.org/10.1371/journal.pbio.3000479) | neuroscience |  | 71 | 1.9 | 12.0 |
| 23 | 1 | [10.1186/s13059-020-02153-6](https://doi.org/10.1186/s13059-020-02153-6) | genomics | yes | 95 | 5.2 | 44.0 |
| 24 | 1 | [10.1038/s41598-019-55976-0](https://doi.org/10.1038/s41598-019-55976-0) | physics | yes | 33 | 1.1 | 5.0 |
| 25 | 1 | [arXiv:1709.03950](https://arxiv.org/abs/1709.03950) | physics/astronomy | yes | 36 | 0.9 | 4.3 |
| 26 | 1 | [arXiv:2609.13110](https://arxiv.org/abs/2609.13110) | physics/cond-mat |  | 42 | 6.7 | 3.1 |
| 27 | 1 | [arXiv:2610.04953](https://arxiv.org/abs/2610.04953) | computer science | yes | 73 | 5.9 | 7.1 |
| 28 | 1 | [arXiv:2610.19239](https://arxiv.org/abs/2610.19239) | computer science |  | 62 | 0.2 | 3.2 |
| 29 | 2 | [10.1371/journal.pgen.1009076](https://doi.org/10.1371/journal.pgen.1009076) | genetics | yes | 73 | 4.3 | 8.1 |
| 30 | 2 | [10.1093/molbev/msab231](https://doi.org/10.1093/molbev/msab231) | evolution | yes | 71 | 5.8 | 8.8 |
| 31 | 2 | [10.7717/peerj.6678](https://doi.org/10.7717/peerj.6678) | ecology | yes | 83 | 0.7 | 4.2 |
| 32 | 2 | [10.1126/sciadv.abi8605](https://doi.org/10.1126/sciadv.abi8605) | physics | yes | 95 | 3.0 | 9.9 |
| 33 | 2 | [10.1186/1471-2105-13-216](https://doi.org/10.1186/1471-2105-13-216) | bioinformatics | yes | 65 | 1.4 | 8.2 |
| 34 | 2 | [10.1371/journal.pone.0278671](https://doi.org/10.1371/journal.pone.0278671) | psychology | yes | 100 | 1.0 | 6.5 |
| 35 | 2 | [10.1016/s2214-109x(21)00392-2](https://doi.org/10.1016/s2214-109x(21)00392-2) | epidemiology | yes | 100 | 1.1 | 2.6 |
| 36 | 2 | [10.1186/s13321-021-00548-6](https://doi.org/10.1186/s13321-021-00548-6) | chemistry | yes | 95 | 3.9 | 17.1 |
| 37 | 2 | [10.1038/s41467-021-27445-8](https://doi.org/10.1038/s41467-021-27445-8) | geophysics | yes | 82 | 3.9 | 18.6 |
| 38 | 2 | [arXiv:2610.05265](https://arxiv.org/abs/2610.05265) | computer science | yes | 45 | 1.2 | 5.3 |
| 39 | 3 | [10.1083/jcb.202011035](https://doi.org/10.1083/jcb.202011035) | cell biology | yes | 100 | 0.6 | 2.5 |
| 40 | 3 | [10.1128/mbio.01654-22](https://doi.org/10.1128/mbio.01654-22) | microbiology | yes | 64 | 7.7 | 15.6 |
| 41 | 3 | [10.1038/s41558-021-01173-9](https://doi.org/10.1038/s41558-021-01173-9) | climate | yes | 68 | 3.0 | 11.2 |
| 42 | 3 | [10.1002/ece3.5742](https://doi.org/10.1002/ece3.5742) | ecology | yes | 100 | 3.1 | 20.3 |
| 43 | 3 | [10.7554/elife.66388](https://doi.org/10.7554/elife.66388) | neuroscience | yes | 91 | 18.2 | 30.6 |
| 44 | 3 | [10.1371/journal.pmed.1003010](https://doi.org/10.1371/journal.pmed.1003010) | medicine | yes | 57 | 4.1 | 9.0 |
| 45 | 3 | [10.1186/s12864-015-2280-z](https://doi.org/10.1186/s12864-015-2280-z) | genomics | yes | 57 | 1.9 | 12.1 |
| 46 | 3 | [10.3389/fpsyg.2022.1073213](https://doi.org/10.3389/fpsyg.2022.1073213) | psychology | yes | 79 | 1.7 | 9.8 |
| 47 | 3 | [arXiv:1709.04065](https://arxiv.org/abs/1709.04065) | astrophysics | yes | 82 | 2.7 | 9.0 |
| 48 | 3 | [arXiv:2609.12862](https://arxiv.org/abs/2609.12862) | physics | yes | 42 | 2.9 | 3.3 |

Machine-readable: `examples/heldout_all.csv` (inputs), `examples/heldout_all_runtime.csv`,
`examples/heldout_all_summary.md` (checklist per paper), `examples/heldout_all_labels.csv` (hand labels).

## 4. Precision by hand (bar item 4)

**Method.** For 36 of the 48 papers (16 from round 1, all 10 of round 2, all 10 of round 3) I judged
**every** checklist item (10 checks × 36 = 360 judgments; ≥36 per check type) against the real source:
the Europe PMC JATS XML / arXiv PDF read independently of the tool (`scripts/raw_sections.py` prints the
availability sections, hyperlinks and request phrases straight from the source), with dead/blocked links
re-checked by `curl` and licenses / releases / repo contents checked with the GitHub, Zenodo and OSF APIs.
A label `A|B` marks a judgment where either answer is defensible (e.g. "no data deposited" for a theory
paper: WARN or N/A); a tool answer inside it counts as **debatable**. Precision = (correct + debatable) / judged.
Reproduce: `python scripts/eval_handcheck.py examples/heldout_all_labels.csv <outdir>`.

`not_future` ("will be made available") fired 0 times in 48 papers, so its precision is unmeasured.
`full_text` was correct 48/48 (always the right article).

### First run of each round (untouched by that round's fixes)

| Round | Papers judged | Judgments | Correct | Debatable | Wrong | Precision |
|---|---|---|---|---|---|---|
| 1 | 16 | 160 | 118 | 9 | 33 | 79% |
| 2 | 10 | 100 | 77 | 9 | 14 | 86% |
| 3 | 10 | 100 | 81 | 10 | 9 | **91%** |
| all | 36 | 360 | 276 | 28 | 56 | 84% |

Per check, round 3 (latest untouched measurement):

| Check | Judged | Correct | Debatable | Wrong | Precision |
|---|---|---|---|---|---|
| data_statement | 10 | 10 | 0 | 0 | 100% |
| code_statement | 10 | 7 | 2 | 1 | 90% |
| not_on_request | 10 | 9 | 1 | 0 | 100% |
| code_link | 10 | 6 | 3 | 1 | 90% |
| links_alive | 10 | 6 | 3 | 1 | 90% |
| code_archived | 10 | 9 | 0 | 1 | 90% |
| code_license | 10 | 9 | 0 | 1 | 90% |
| version_pinned | 10 | 9 | 0 | 1 | 90% |
| repo_checks | 10 | 9 | 0 | 1 | 90% |
| data_deposited | 10 | 7 | 1 | 2 | 80% |
| **all** | 100 | 81 | 10 | 9 | **91%** |

Per check, all three first runs combined:

| Check | Judged | Correct | Debatable | Wrong | Precision |
|---|---|---|---|---|---|
| data_statement | 36 | 34 | 0 | 2 | 94% |
| code_statement | 36 | 21 | 5 | 10 | 72% |
| not_on_request | 36 | 33 | 1 | 2 | 94% |
| code_link | 36 | 22 | 6 | 8 | 78% |
| links_alive | 36 | 23 | 4 | 9 | 75% |
| code_archived | 36 | 30 | 0 | 6 | 83% |
| code_license | 36 | 31 | 0 | 5 | 86% |
| version_pinned | 36 | 30 | 0 | 6 | 83% |
| repo_checks | 36 | 32 | 2 | 2 | 94% |
| data_deposited | 36 | 20 | 10 | 6 | 83% |
| **all** | 360 | 276 | 28 | 56 | **84%** |

### After fixes (final code, live run)

All 360 judgments correct or debatable (327 correct, 33 debatable, 0 wrong); every check 100%.
The development sets are unchanged (91% on the original 13-paper set, 100% on its 5-paper follow-up).
**Caveat:** these 360 judgments are the ones the fixes were made against, so this is a regression
check, not an unbiased estimate. The unbiased estimate is the round-3 first run (91%); expect new
journal formats to keep surfacing gaps at roughly that rate.

### Wrong judgments found and how each was fixed (all have regression tests in `tests/test_regressions_heldout.py`)

| Paper | Wrong judgment | Root cause → fix |
|---|---|---|
| Cell Rep 10.1016/j.celrep.2019.09.064 | fake dead link `github.com/nservant/HiC-ProIGB`; tools in key-resources table counted as own code; "mice and plasmids on request" flagged; `GSE: 123209` missed | JATS table cells concatenated → block-level separators; ownership needs a sentence-local cue ("available at", "our code"); materials-only requests excluded; accession spacing normalised |
| Genome Biol 10.1186/s13059-020-02153-6 | "archived in Zenodo [50]" not seen; fake dead `…GetOrganelle.git587c1c…` | numbered citations resolved to the repository DOI in the reference (incl. plain-text DOIs); table separators |
| Ecol Evol 10.1002/ece3.9623 | GitHub URL "dead" | printed URL used U+2010 hyphen → dashes normalised |
| PLoS CB 10.1371/journal.pcbi.1002284 | code on Google Code missed; "dead" on HTTP 503 | `code.google.com` host + "Software" heading; Google Code archive bucket checked; 5xx = unverifiable, not dead; license stated in paper text now read |
| PLoS One 10.1371/journal.pone.0156543 | third-party idock / PyRx counted as own code | "was downloaded from" and "(v0.8) from (" recognised as tool citations |
| eNeuro 10.1523/eneuro.0202-21.2021 | cited package ssqueezepy gave "version pinned" | ownership cue limited to the link's own sentence; inline `pip install` counts as README run step |
| R Soc Open Sci 10.1098/rsos.200664 | OSF "analysis codes" missed, personal github.io counted as code | archives in a statement mentioning code count as code; `github.io` = web page; OSF API for license |
| NAR 10.1093/nar/gku294, BMC Genomics 10.1186/s12864-015-2280-z | web server never checked | body URLs introduced by "available at" are checked; web-service-only papers get WARN, not FAIL |
| arXiv 2610.04953 | fake dead `EDISCO.40th` | PDF line join no longer joins after "." |
| arXiv 2610.04953, 2609.12862 | "methods mention crystal structure"/"we measured" → data FAIL | needs a data-type term *and* a collection verb |
| PeerJ 10.7717/peerj.6678 | "R scripts … as a Supplemental File" missed | code mentions inside data statements; supplement-only code → WARN |
| Sci Adv 10.1126/sciadv.abi8605 | statement missed | Science-style run-in heading ("… interests. Data and materials availability: …") |
| BMC Bioinf 10.1186/1471-2105-13-216 | statement missed; then whole paper N/A | "Availability and requirements" heading; overlapping-span bug; BMC tags software papers `product-review` (not treated as non-research) |
| Lancet GH 10.1016/s2214-109x(21)00392-2, JCB 10.1083/jcb.202011035 | review/commentary failed for missing statements | JATS `article-type` review/editorial/commentary → N/A; "Data sharing" heading added |
| Mol Biol Evol 10.1093/molbev/msab231 | "accession codes" read as code | excluded; China NGDC `PRJCA`/`CRA` accessions added |
| J Cheminform 10.1186/s13321-021-00548-6 | "datasets and code … GitHub/Zenodo" → data not deposited | "datasets" accepted for data-in-code-archive rule |
| arXiv 1709.04065 (FLaapLUC) | fake dead `doi.org/10.5281/zenodo`; own repo unclaimed; arXiv DOI field was the Zenodo DOI | DOI stems re-joined across lines; de-hyphenation (`avail-\nable`), ligatures (`ﬂ`), `github.com /x`; repo named in the title = own code; repository DOIs from arXiv metadata treated as code archives |
| arXiv 2610.05265 | "license not checkable for this host" for a 404 repo | message now says the repository was not reachable |

Real problems the tool found and I confirmed (these are what an editor wants): dead links in 8 of the 48
papers, e.g. retired web servers (tartaglialab.com tools, probis benchmark page), a 404 docking tool
repo (idock), a 404 anonymous review repo cited in a preprint, a deleted project page (basp-group.github.io),
IMG URL, a bit.ly link that now lands on a 404; data/code "on request" in 5 papers; unlicensed code repos
(Nat Clim Chang 10.1038/s41558-021-01173-9, PLoS Genet 10.1371/journal.pgen.1009076).

## 5. Message review (bar item 5)

Every message template was reviewed for accuracy and tone:
- "dead: url (404)" became "not reachable when checked: url (HTTP 404)" or "(host name no longer resolves)".
- Links that block bots, time out or return 5xx are "could not be verified automatically", never dead.
- "only bare git-host links" became "code is linked only on a code-hosting site; no archived snapshot with a DOI (e.g. Zenodo, Software Heritage) was found".
- Ambiguous cases are WARN with "(please check)" instead of FAIL: unclaimed code links, web-service-only papers, code in supplements.
- Every report starts with: "Automated screening. A FAIL means the item could not be found or verified automatically; please confirm against the paper before contacting the authors."
- No message claims an "error" by the authors. Archive / version / repo-hygiene items are WARN (recommendations), never FAIL.

## 6. CI (bar item 6)

`.github/workflows/ci.yml`: uv-managed Python on Ubuntu (3.9, 3.12, 3.13) and macOS (3.9, 3.12); runs the
89 offline tests (recorded HTTP fixtures, no network) and a CLI smoke test. All green.
(`actions/setup-python` no longer provides 3.9 on Ubuntu 26.04 runners, hence uv.)

## Known limitations

- **New journal formats keep appearing.** Each round surfaced 1–3 new heading or markup styles. Expect about 90% precision on unseen journals, not 100%.
- **Bot-blocking hosts** are reported as unverifiable WARN even when alive in a browser. Examples: SourceForge, SciCrunch/identifiers.org, some government portals.
- **Third-party vs own code** is heuristic. It uses sentence-local cues, version cues, the repo owner, and the repo name appearing in the title. A link with no cue gives WARN "please check" rather than a verdict.
- **"Computational?"** is a keyword count. It decides whether a missing code link is FAIL or N/A. Statistics-only papers (SPSS, GraphPad) are treated as non-computational.
- **"Data deposited"** cannot tell "no new data" (theory, software, public benchmarks) from "data not shared". Those papers get WARN where a human might say N/A. This accounts for most debatable labels.
- **Not read:** supplementary files, publisher-only HTML statements, and figure/table images.
- **Not checked:** FTP links.
- **Not supported:** closed-access papers with no open-access copy (metadata only).
- **Version matching** uses releases/tags up to 30 days after publication, pinned URLs, or versioned archives. It does not compare code with the paper.
- **OSF projects** are counted as archived, but unlike registrations they can still change.
- **`not_future`** ("will be made available") was never triggered in 48 papers, so its precision is unmeasured.
- **GitHub API:** about 4 calls per GitHub repo, so set `GITHUB_TOKEN` for batches over about 15 papers. The tool makes no search-API calls, so the 30/min search limit does not apply.
