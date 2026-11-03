# paper-repro-auditor

`paper-audit` checks whether a publication links everything needed to reproduce its
computational results, and writes a checklist report (Markdown + JSON).

It is aimed at journal reproducibility/data editors and reviewers. Give it one paper, or a
CSV of DOIs for a whole issue.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "git+https://github.com/Yenula-W/paper-repro-auditor"   # Python >= 3.9; deps: requests, pypdf
paper-audit 10.1371/journal.pone.0224321  # first audit; report in audit-out/
```

More inputs:

```bash
export GITHUB_TOKEN=...                   # optional; avoids GitHub's 60 req/h anonymous limit
paper-audit 10.1038/s41586-021-03819-2    # DOI
paper-audit arXiv:1706.03762              # arXiv id
paper-audit paper.pdf                     # local PDF (or a PDF URL)
paper-audit --batch dois.csv -o issue-42/ # batch: CSV with a 'doi' column (or first column)
```

Output goes to `audit-out/` by default: one `<doi>.md` and `<doi>.json` per paper. Batch mode
also writes `summary.csv` and `summary.md` (one row per paper, one column per check). A paper
that fails does not stop the batch; it gets an `error` entry in `summary.csv`.

Flags: `--no-clone` skips the repo checks, `--json` prints JSON instead of Markdown, `-q` is quiet.
Exit codes: 0 = report written, 2 = input could not be audited (message on stderr, no traceback;
set `PAPER_AUDIT_DEBUG=1` to see one). Batch `summary.csv` also records runtime and output size per paper.

## What it checks

| Check | PASS | WARN | FAIL |
|---|---|---|---|
| `full_text` | open-access full text found | | no OA text (only metadata audited) |
| `data_statement` | "Data availability" / "Availability of data and materials" / "Data Records" … section found | | none |
| `code_statement` | "Code availability" / "Availability and implementation" section, or a code link inside an availability statement | code linked only in body text | none, and paper looks computational |
| `not_on_request` | no "available (up)on request" / "from the corresponding author" | phrase only outside the statements | phrase in a statement, or no deposit at all |
| `not_future` (only if triggered) | | | "will be made available" / "upon publication" |
| `code_link` | link to the paper's own code (GitHub/GitLab/Zenodo software/SWH/Code Ocean …) | statement points only to a website or web server | code "on request", or computational paper with no code link |
| `links_alive` | every audited link resolves | some links blocked (403/429/timeouts) | 404/410 or the host no longer resolves |
| `code_archived` | code has a DOI or persistent snapshot (Zenodo, Figshare, Software Heritage …) | bare GitHub/GitLab only | |
| `code_license` | license on the repo or archive | | no license detected |
| `version_pinned` | URL pins a tag/commit, the archive is versioned, or a GitHub release exists up to 30 days after publication | none; also notes "repo changed after publication" | |
| `repo_checks` | blobless shallow clone: dependency file, README with run steps, entry point, license file | some missing | clone failed |
| `data_deposited` | repository link (Dryad, Zenodo, OSF, Figshare, GEO, …) or accession (GSE, PRJNA, PXD, EGA, …) | data "in the paper/SI" only, or data only in a git repo with no archive | "on request", or methods describe new data (we collected / sequenced …) but nothing deposited |

The score is (PASS + 0.5 × WARN) / applicable checks × 100. N/A checks are not counted.

### How it works

1. **Resolve the input** (`sources.py`). For a DOI it reads Crossref metadata and OpenAlex,
   then gets full text in this order:
   - Europe PMC JATS XML (best, because it keeps section titles and hyperlink targets);
   - open-access PDFs from OpenAlex, then Unpaywall (only if `UNPAYWALL_EMAIL` is set), then
     Crossref links.

   arXiv ids use the arXiv API and PDF. PDFs are parsed with `pypdf`, including link
   annotations, so hyperlinks hidden behind text are found. URLs broken across lines are rejoined.
2. **Extract** (`extract.py`):
   - availability statements, found by heading;
   - links from those statements, plus repository-type links anywhere in the body (the
     reference list is excluded);
   - accession numbers;
   - red-flag phrases;
   - a "looks computational" signal (R/Python/models/simulations/training …).
3. **Resolve links** (`resolve.py`, 8 links in parallel):
   - GitHub API: exists, license, stars, releases near the publication date, commits after
     publication;
   - GitLab API;
   - Zenodo API: license, version, software vs dataset;
   - Figshare API: item type and license;
   - plain HTTP for everything else.

   Links to cited third-party tools (for example "TensorFlow v.1 (url)", "WRF v3.9.1.1 …
   here: url", CRAN packages in the body, or very popular repos after the first) are marked
   `cited tool`. They do not count as the paper's code.
4. **Light repo checks** (`repocheck.py`). This runs only on the paper's own repos (at most 2).
   It does a `git clone --depth 1 --filter=blob:none --no-checkout`, so only the file list and
   README are downloaded; AlphaFold takes about 1 s. The module is self-contained, with a
   stable interface (`check_repo(url, ref) -> {"checks": [{"id","passed","detail"}]}`,
   `scan_dir(path)`), so it can be swapped for the `repro-debt-scanner` package later.
5. **Checklist + report** (`audit.py`, `report.py`).

Only open APIs are used: Crossref, OpenAlex, Europe PMC, arXiv, Unpaywall (optional), GitHub,
GitLab, Zenodo and Figshare. No paid services.

### Caching / offline

The HTTP layer (`http.py`) supports three modes, set by environment variable:
- `PAPER_AUDIT_CACHE=<dir>`: read-through cache, useful when re-running a batch;
- `PAPER_AUDIT_RECORD=<dir>`: record every response;
- `PAPER_AUDIT_REPLAY=<dir>`: serve only recorded responses, with no network at all.

The tests use replay mode.

## Hand-checked results

The tool was run on 13 open-access papers across fields. For each paper I read the
availability sections and links in the source (Europe PMC XML / arXiv PDF) by hand. Dead or
blocked links were re-checked with `curl` and the GitHub API. I compared 7 checklist items per
paper, 91 judgments in total.

Labels are in [`examples/handcheck_labels.csv`](examples/handcheck_labels.csv), including a
note per paper. Reproduce the comparison with:

```bash
paper-audit --batch examples/handcheck.csv -o out/batch
python scripts/eval_handcheck.py examples/handcheck_labels.csv out/batch
```

| Paper | Field | data stmt | code stmt | not on request | code link | links alive | code archived | data deposited | Agree |
|---|---|---|---|---|---|---|---|---|---|
| 10.7554/elife.62362 | neuroscience | PASS | PASS | **WARN** (hand: PASS) | PASS | **WARN** (hand: PASS) | WARN | PASS | 5/7 |
| 10.1038/s41467-022-34126-7 | climate | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | 7/7 |
| 10.1002/ece3.6827 | ecology | PASS | FAIL | PASS | FAIL | PASS | N/A | PASS | 7/7 |
| 10.1136/bmjopen-2020-045805 | clinical | PASS | N/A | FAIL | N/A | N/A | N/A | FAIL | 7/7 |
| 10.1371/journal.pone.0224321 | psychology | PASS | N/A | PASS | N/A | PASS | N/A | PASS | 7/7 |
| 10.1038/s41598-020-77660-4 | complex systems | PASS | PASS | FAIL | FAIL | PASS | N/A | FAIL | 7/7 |
| 10.1371/journal.pcbi.1005898 | comp. biology | PASS | PASS | PASS | PASS | PASS | PASS | **WARN** (hand: N/A) | 6/7 |
| 10.1093/bioinformatics/btz570 | bioinformatics | FAIL | PASS | PASS | WARN | **WARN** (hand: FAIL) | N/A | **WARN** (hand: N/A) | 5/7 |
| 10.1038/s41467-021-27615-8 | cancer genomics | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 7/7 |
| 10.1038/s41597-022-01730-7 | geochemistry | PASS | PASS | PASS | PASS | **WARN** (hand: PASS) | WARN | PASS | 6/7 |
| 10.1038/s41586-021-03819-2 | structural bio | PASS | PASS | PASS | PASS | FAIL | WARN | PASS | 7/7 |
| arXiv:1706.03762 | machine learning | FAIL | WARN | PASS | PASS | PASS | WARN | **WARN** (hand: N/A) | 6/7 |
| arXiv:1512.03385 | computer vision | FAIL | FAIL | PASS | FAIL | N/A | N/A | **WARN** (hand: N/A) | 6/7 |

**Agreement: 83/91 = 91%.** By check:
- data statement: 13/13
- code statement: 13/13
- code link: 13/13
- code archived: 13/13
- not on request: 12/13
- links alive: 10/13
- data deposited: 9/13

**Caveat:** I tuned the rules on this set, so these numbers are optimistic. I then ran a
**held-out set of 5 more papers** (eLife, Ecol Evol, BMJ Open, PLOS CB, Nat Commun):
- first run: 34/35;
- the one miss was data shipped inside a GitHub + Software Heritage repo, which was not
  counted as deposited;
- after a rule fix: 35/35.

See [`examples/heldout_labels.csv`](examples/heldout_labels.csv).

Real problems it caught (all confirmed by hand):
- dead data links in AlphaFold: `cdn.rcsb.org/.../bc-40.out` returns 404 and
  `ftp.wwpdb.org` no longer resolves;
- a retired Copernicus CDS URL and a 404 ARM DOI target in the climate paper;
- data *and* code "on request" (Sci Rep);
- an unlicensed, unarchived code repo (Sci Data);
- a 24-character stub README (Nat Commun genomics).

### Known limitations (where the disagreements come from)

- **Bot-blocked links** (identifiers.org/SciCrunch 403, some DOIs) and timeouts are reported
  as WARN "unverifiable", never as dead. A server that is down shows as WARN, not FAIL.
- **"Data deposited" for papers with no new data.** Software papers and ML papers that use
  public benchmarks get WARN, where a human would say N/A.
- **"On request" scope.** The phrase is matched anywhere in the text, so "cloud images
  provided upon request" gives a WARN.
- **"Computational" heuristic.** This decides whether a missing code link is a FAIL or N/A. It
  counts mentions of R / Python / GLMMs / simulations / training and similar. Papers that
  only use SPSS are treated as non-computational. Papers that fit models in R and share no
  code get FAIL, which matches stricter journal code policies.
- **Third-party tool detection** is heuristic: version cues near the URL, popularity, and
  registries.
- **Closed-access papers** without an OA copy only get metadata (`full_text` FAIL).
  Publisher PDFs sometimes block downloads; a local PDF always works.
- **Version matching** uses GitHub releases (up to 30 days after publication), pinned URLs or
  versioned archives. It does not diff code against the paper.
- Supplementary files and Data Availability text that exists only on publisher HTML pages
  (not in XML/PDF) are not read.

## Development

```bash
uv venv -p 3.11 .venv && uv pip install -p .venv -e '.[test]'
.venv/bin/pytest -q          # 13 tests, no network (recorded fixtures in tests/fixtures/)
```

To add a fixture, record it:

```bash
PAPER_AUDIT_RECORD=tests/fixtures/<name> paper-audit <doi> --no-clone
```

Authorization headers are never part of cache keys or saved files.

Layout:
- `src/paper_audit/sources.py`: input to metadata + text
- `extract.py`: statements, links, flags
- `resolve.py`: link checks
- `repocheck.py`: swappable repo checks
- `audit.py`: checklist
- `report.py`: Markdown output
- `cli.py`: command line
