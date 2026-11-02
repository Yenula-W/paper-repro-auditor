"""paper-audit command line."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from .audit import audit
from .report import CHECK_COLS, batch_markdown, status_map, to_markdown


def _slug(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", s).strip("_")[:80]


def _read_inputs(path: str) -> list:
    rows = []
    with open(path, newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        has_header = bool(re.search(r"(?i)\b(doi|id|input|paper|arxiv|pdf)\b", sample.splitlines()[0] if sample else ""))
        reader = csv.reader(f)
        if has_header:
            header = [h.strip().lower() for h in next(reader)]
            col = next((i for i, h in enumerate(header) if h in ("doi", "input", "id", "paper", "arxiv", "pdf")), 0)
        else:
            col = 0
        for row in reader:
            if row and row[col].strip() and not row[col].startswith("#"):
                rows.append(row[col].strip())
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="paper-audit",
                                 description="Audit whether a paper links everything needed to reproduce its computational results.")
    ap.add_argument("input", nargs="?", help="DOI, arXiv id, or PDF path/URL")
    ap.add_argument("--batch", metavar="CSV", help="CSV with one DOI/arXiv id/PDF per row (column 'doi' or first column)")
    ap.add_argument("-o", "--out", default="audit-out", help="output directory (default: audit-out)")
    ap.add_argument("--no-clone", action="store_true", help="skip shallow-cloning linked repos")
    ap.add_argument("--json", action="store_true", help="print JSON to stdout instead of Markdown")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args(argv)
    if not a.input and not a.batch:
        ap.error("give an INPUT or --batch CSV")
    log = (lambda *_: None) if a.quiet else (lambda m: print(f"  · {m}", file=sys.stderr))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    if a.input:
        r = audit(a.input, clone=not a.no_clone, log=log)
        base = out / _slug(r["paper"].get("doi") or r["paper"].get("arxiv_id") or Path(a.input).stem)
        md = to_markdown(r)
        Path(f"{base}.json").write_text(json.dumps(r, indent=2))
        Path(f"{base}.md").write_text(md)
        print(json.dumps(r, indent=2) if a.json else md)
        print(f"wrote {base}.md / .json", file=sys.stderr)
        return 0

    inputs = _read_inputs(a.batch)
    results = []
    for n, inp in enumerate(inputs, 1):
        print(f"[{n}/{len(inputs)}] {inp}", file=sys.stderr)
        try:
            r = audit(inp, clone=not a.no_clone, log=log)
        except Exception as e:  # noqa: BLE001 - keep batch going
            r = {"input": inp, "error": f"{type(e).__name__}: {e}"}
            results.append(r)
            continue
        base = out / _slug(r["paper"].get("doi") or r["paper"].get("arxiv_id") or inp)
        Path(f"{base}.json").write_text(json.dumps(r, indent=2))
        Path(f"{base}.md").write_text(to_markdown(r))
        results.append(r)
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["input", "doi", "title", "score", "pass", "warn", "fail"] + CHECK_COLS + ["error"])
        for r in results:
            if "error" in r:
                w.writerow([r["input"]] + [""] * (6 + len(CHECK_COLS)) + [r["error"]])
                continue
            m = status_map(r)
            s = r["summary"]
            w.writerow([r["paper"]["input"], r["paper"].get("doi") or "", r["paper"].get("title", "")[:150],
                        s["score"], s["pass"], s["warn"], s["fail"]] + [m.get(c, "") for c in CHECK_COLS] + [""])
    (out / "summary.md").write_text(batch_markdown(results))
    print(batch_markdown(results))
    print(f"wrote {len(results)} reports + summary.csv/summary.md to {out}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
