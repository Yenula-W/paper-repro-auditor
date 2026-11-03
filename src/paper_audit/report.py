"""Render audit results as Markdown (single paper and batch summary)."""
from __future__ import annotations

from typing import List

ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "N/A": "➖"}


def _esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def to_markdown(r: dict) -> str:
    p, s = r["paper"], r["summary"]
    ident = p.get("doi") or p.get("arxiv_id") or p["input"]
    lines = [
        f"# Reproducibility audit: {p.get('title') or ident}",
        "",
        f"- **Identifier:** {ident}",
        f"- **Venue / date:** {p.get('journal') or '?'} / {p.get('published') or '?'}",
        f"- **Full text:** {p.get('text_source')}",
        f"- **Score:** {s['score']}/100 ({s['pass']} pass, {s['warn']} warn, {s['fail']} fail)",
        "",
        "> Automated screening. A FAIL means the item could not be found or verified automatically;",
        "> please confirm against the paper before contacting the authors.",
        "",
        "## Checklist",
        "",
        "| | Check | Status | Detail |",
        "|---|---|---|---|",
    ]
    for i in r["checklist"]:
        lines.append(f"| {ICON.get(i['status'], '')} | {i['label']} | {i['status']} | {_esc(i['detail'])[:300]} |")
    ev = r["evidence"]
    if ev["statements"]:
        lines += ["", "## Availability statements", ""]
        for st in ev["statements"]:
            lines += [f"**{st['heading']}** ({st['kind']})", "", "> " + st["text"][:1200], ""]
    if ev["links"]:
        lines += ["", "## Links", "", "| URL | Type | Alive | Archived DOI | License | Version | Notes |",
                  "|---|---|---|---|---|---|---|"]
        for l in ev["links"]:
            alive = {True: "yes", False: f"**no** ({l['status']})", None: f"? ({l['status']})"}[l["alive"]]
            ver = l.get("pinned_ref") or ", ".join(l.get("releases_before_pub") or [])
            if l.get("commits_after_pub"):
                ver += " (changed after pub.)"
            lines.append(f"| {_esc(l['url'])} | {l['repo_type']}/{l['kind']}{' (stmt)' if l['in_statement'] else ''}{' (cited tool)' if l.get('third_party') else ''} | "
                         f"{alive} | {'yes' if l['archived_doi'] else ''} | {l.get('license') or ''} | "
                         f"{_esc(ver)} | {_esc('; '.join(l.get('notes') or []))[:120]} |")
    if ev.get("accessions"):
        lines += ["", "**Accessions:** " + ", ".join(f"{a['id']} ({a['db']})" for a in ev["accessions"])]
    for r_ in ev.get("repos") or []:
        lines += ["", f"## Repo check: {r_.get('url')}", ""]
        if r_.get("error"):
            lines.append(f"- error: {r_['error']}")
        for c in r_.get("checks", []):
            lines.append(f"- {ICON['PASS'] if c['passed'] else ICON['FAIL']} `{c['id']}`: {c['detail']}")
    flags = [("Available-on-request phrases", ev["on_request"]), ("Future-release phrases", ev["future_release"])]
    for name, vals in flags:
        if vals:
            lines += ["", f"**{name}:**", ""] + [f"- …{_esc(v)}…" for v in vals]
    if p.get("warnings"):
        lines += ["", "**Warnings:** " + "; ".join(p["warnings"])]
    lines += ["", f"<sub>{r['tool']} · {r['audited_at']}</sub>", ""]
    return "\n".join(lines)


CHECK_COLS = ["full_text", "data_statement", "code_statement", "not_on_request", "code_link",
              "links_alive", "code_archived", "code_license", "version_pinned", "repo_checks", "data_deposited"]


def status_map(r: dict) -> dict:
    return {i["id"]: i["status"] for i in r.get("checklist", [])}


def check_cols(results: List[dict]) -> List[str]:
    """Batch columns; data_deposited only when the experimental checks were run."""
    exp = any(r.get("experimental_checks") for r in results)
    return [c for c in CHECK_COLS if exp or c != "data_deposited"]


def batch_markdown(results: List[dict]) -> str:
    CHECK_COLS = check_cols(results)   # noqa: N806
    head = ["Paper", "Score"] + CHECK_COLS
    lines = ["# Batch reproducibility audit", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['input']} | ERROR | " + _esc(r["error"])[:100] + " |" + " |" * (len(CHECK_COLS) - 1))
            continue
        p = r["paper"]
        m = status_map(r)
        ident = p.get("doi") or p.get("arxiv_id") or p["input"]
        lines.append(f"| {ident} | {r['summary']['score']} | " +
                     " | ".join(ICON.get(m.get(c, ""), "") or "" for c in CHECK_COLS) + " |")
    return "\n".join(lines) + "\n"
