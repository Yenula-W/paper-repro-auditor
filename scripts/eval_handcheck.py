"""Compare batch audit output with hand-checked labels.

usage: python scripts/eval_handcheck.py examples/handcheck_labels.csv out/batch
"""
import csv
import json
import re
import sys
from pathlib import Path

labels, outdir = sys.argv[1], Path(sys.argv[2])
rows = list(csv.DictReader(open(labels)))
checks = [c for c in rows[0] if c not in ("id", "notes")]
agree = total = 0
per_check = {c: [0, 0] for c in checks}
lines = ["| Paper | " + " | ".join(checks) + " | Agree |", "|---" * (len(checks) + 2) + "|"]
for r in rows:
    pid = r["id"].replace("arXiv:", "")
    f = outdir / (re.sub(r"[^\w.-]+", "_", pid).strip("_") + ".json")
    got = {i["id"]: i["status"] for i in json.load(open(f))["checklist"]}
    cells, n_ok = [], 0
    for c in checks:
        exp, g = r[c], got.get(c, "N/A")
        ok = exp == g
        n_ok += ok
        per_check[c][0] += ok
        per_check[c][1] += 1
        cells.append(g if ok else f"**{g}** (hand: {exp})")
    agree += n_ok
    total += len(checks)
    lines.append(f"| {r['id']} | " + " | ".join(cells) + f" | {n_ok}/{len(checks)} |")
print("\n".join(lines))
print()
print("Per check: " + ", ".join(f"{c} {a}/{n}" for c, (a, n) in per_check.items()))
print(f"\nOverall agreement: {agree}/{total} = {100 * agree / total:.0f}%")
