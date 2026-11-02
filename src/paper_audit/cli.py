"""paper-audit command line."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

from .audit import audit
from .report import CHECK_COLS, batch_markdown, status_map, to_markdown


def _slug(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", s).strip("_")[:80]


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _read_inputs(path: str) -> list:
    """One input per row: column named doi/input/id/paper/arxiv/pdf, else the first column."""
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        raise ValueError(f"cannot read batch file {path!r}: {e.strerror or e}") from None
    text = _decode(raw).replace("\x00", "")
    lines = text.splitlines()
    if not lines:
        return []
    rows = list(csv.reader(lines))
    header = [h.strip().lower() for h in rows[0]] if rows and rows[0] else []
    names = ("doi", "input", "id", "paper", "arxiv", "pdf")
    if any(h in names for h in header):
        col = next(i for i, h in enumerate(header) if h in names)
        rows = rows[1:]
    else:
        col = 0
    out = []
    for row in rows:
        if len(row) > col:
            v = row[col].strip()
            if v and not v.startswith("#"):
                out.append(v)
    return out


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 2


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
    if a.input is None and not a.batch:
        ap.error("give an INPUT or --batch CSV")
    log = (lambda *_: None) if a.quiet else (lambda m: print(f"  · {m}", file=sys.stderr))
    out = Path(a.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return _fail(f"cannot create output directory {str(out)!r}: {e.strerror or e}")

    if a.input is not None and a.batch is None:
        try:
            r = audit(a.input, clone=not a.no_clone, log=log)
        except ValueError as e:
            return _fail(str(e))
        except Exception as e:  # noqa: BLE001 - never show a traceback to end users
            if os.environ.get("PAPER_AUDIT_DEBUG"):
                raise
            return _fail(f"audit failed ({type(e).__name__}: {e}). Set PAPER_AUDIT_DEBUG=1 for details.")
        base = out / _slug(r["paper"].get("doi") or r["paper"].get("arxiv_id") or Path(a.input).stem)
        md = to_markdown(r)
        Path(f"{base}.json").write_text(json.dumps(r, indent=2))
        Path(f"{base}.md").write_text(md)
        print(json.dumps(r, indent=2) if a.json else md)
        print(f"wrote {base}.md / .json", file=sys.stderr)
        return 0

    try:
        inputs = _read_inputs(a.batch)
    except ValueError as e:
        return _fail(str(e))
    if not inputs:
        print("warning: batch file contains no inputs", file=sys.stderr)
    results = []
    for n, inp in enumerate(inputs, 1):
        print(f"[{n}/{len(inputs)}] {inp}", file=sys.stderr)
        t0 = time.monotonic()
        try:
            r = audit(inp, clone=not a.no_clone, log=log)
        except Exception as e:  # noqa: BLE001 - keep batch going
            r = {"input": inp, "error": f"{type(e).__name__}: {e}",
                 "runtime_s": round(time.monotonic() - t0, 1)}
            results.append(r)
            continue
        r["runtime_s"] = round(time.monotonic() - t0, 1)
        base = out / _slug(r["paper"].get("doi") or r["paper"].get("arxiv_id") or inp)
        md = to_markdown(r)
        js = json.dumps(r, indent=2)
        Path(f"{base}.json").write_text(js)
        Path(f"{base}.md").write_text(md)
        r["output_bytes"] = len(js.encode()) + len(md.encode())
        results.append(r)
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["input", "doi", "title", "score", "pass", "warn", "fail"] + CHECK_COLS
                   + ["runtime_s", "output_bytes", "error"])
        for r in results:
            if "error" in r:
                w.writerow([r["input"]] + [""] * (6 + len(CHECK_COLS)) + [r["runtime_s"], "", r["error"]])
                continue
            m = status_map(r)
            s = r["summary"]
            w.writerow([r["paper"]["input"], r["paper"].get("doi") or "", r["paper"].get("title", "")[:150],
                        s["score"], s["pass"], s["warn"], s["fail"]] + [m.get(c, "") for c in CHECK_COLS]
                        + [r["runtime_s"], r.get("output_bytes", ""), ""])
    (out / "summary.md").write_text(batch_markdown(results))
    print(batch_markdown(results))
    print(f"wrote {len(results)} reports + summary.csv/summary.md to {out}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
