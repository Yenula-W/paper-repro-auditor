"""Compare batch audit output with hand-checked labels.

usage: python scripts/eval_handcheck.py LABELS.csv OUTDIR [--markdown]

A label like "WARN|N/A" means either answer is defensible: a match there counts as
"debatable", an exact single-label match as "correct", anything else as "wrong".
Blank label cells are not judged.
"""
import csv
import json
import re
import sys
from pathlib import Path

labels, outdir = sys.argv[1], Path(sys.argv[2])
rows = list(csv.DictReader(open(labels)))
checks = [c for c in rows[0] if c not in ("id", "notes")]
tally = {c: {"correct": 0, "debatable": 0, "wrong": 0} for c in checks}
lines = ["| Paper | " + " | ".join(checks) + " | Correct |", "|---" * (len(checks) + 2) + "|"]
wrong_list = []
for r in rows:
    pid = r["id"].replace("arXiv:", "")
    f = outdir / (re.sub(r"[^\w.-]+", "_", pid).strip("_") + ".json")
    got = {i["id"]: i["status"] for i in json.load(open(f))["checklist"]}
    cells, ok_n, n = [], 0, 0
    for c in checks:
        exp = (r.get(c) or "").strip()
        if not exp:
            cells.append("")
            continue
        g = got.get(c, "N/A")
        alts = exp.split("|")
        n += 1
        if len(alts) == 1 and g == exp:
            verdict = "correct"
        elif len(alts) > 1 and g in alts:
            verdict = "debatable"
        else:
            verdict = "wrong"
            wrong_list.append(f"{r['id']} {c}: tool {g}, hand {exp}")
        tally[c][verdict] += 1
        ok_n += verdict != "wrong"
        cells.append(g if verdict == "correct" else (f"{g} (~)" if verdict == "debatable" else f"**{g}** (hand: {exp})"))
    lines.append(f"| {r['id']} | " + " | ".join(cells) + f" | {ok_n}/{n} |")
print("\n".join(lines))
print("\n| Check | Judged | Correct | Debatable | Wrong | Precision (correct+debatable) |\n|---|---|---|---|---|---|")
tot = {"correct": 0, "debatable": 0, "wrong": 0}
for c, t in tally.items():
    n = sum(t.values())
    for k in tot:
        tot[k] += t[k]
    if n:
        print(f"| {c} | {n} | {t['correct']} | {t['debatable']} | {t['wrong']} | {100 * (n - t['wrong']) / n:.0f}% |")
n = sum(tot.values())
print(f"| **all** | {n} | {tot['correct']} | {tot['debatable']} | {tot['wrong']} | **{100 * (n - tot['wrong']) / n:.0f}%** |")
if wrong_list:
    print("\nWrong:\n" + "\n".join("- " + w for w in wrong_list))
print(f"\nOverall: {tot['correct']} correct, {tot['debatable']} debatable, {tot['wrong']} wrong of {n} "
      f"= {100 * (n - tot['wrong']) / n:.0f}% acceptable, {100 * tot['correct'] / n:.0f}% exactly correct")
