"""Orchestrate one audit and turn evidence into a checklist."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict
from typing import List, Optional

from . import __version__
from .extract import extract
from .repocheck import check_repo
from .resolve import resolve_link
from .sources import Paper, load_paper

PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "N/A"
CODE_TYPES = {"github", "gitlab", "bitbucket", "codeocean", "swh", "sourceforge", "pypi", "cran", "bioconductor"}
MAX_LINKS = 30
MAX_CLONES = 3


@dataclass
class Item:
    id: str
    label: str
    status: str
    detail: str = ""


def _is_code(l: dict) -> bool:
    return l["repo_type"] in CODE_TYPES or l["kind"] == "code"


def _is_data(l: dict) -> bool:
    return not _is_code(l) and (l["kind"] in ("data", "archive") or (l["in_statement"] and l["kind"] == "doi"))


def build_checklist(paper: dict, ex: dict, links: List[dict], repos: List[dict]) -> List[Item]:
    items: List[Item] = []
    add = lambda *a: items.append(Item(*a))  # noqa: E731
    if paper["text_source"] == "none":
        add("full_text", "Full text retrieved", FAIL, "; ".join(paper["warnings"]) or "no open-access text")
        return items
    add("full_text", "Full text retrieved", PASS, paper["text_source"])

    stmts = ex["statements"]
    data_st = [s for s in stmts if s["kind"] in ("data", "both")]
    code_st = [s for s in stmts if s["kind"] in ("code", "both")]
    computational = ex["computational_hits"] >= 3
    code_links = [l for l in links if _is_code(l)]
    data_links = [l for l in links if _is_data(l)]
    code_in_stmt = [l for l in code_links if l["in_statement"]]

    add("data_statement", "Data availability statement", PASS if data_st else FAIL,
        data_st[0]["text"][:200] if data_st else "no data availability section found")

    if code_st:
        add("code_statement", "Code availability statement", PASS, code_st[0]["text"][:200])
    elif code_in_stmt:
        add("code_statement", "Code availability statement", PASS, "code link given in availability statement")
    elif code_links:
        add("code_statement", "Code availability statement", WARN, "no dedicated statement; code linked in body text")
    else:
        add("code_statement", "Code availability statement", FAIL if computational else NA,
            "none found" + ("" if computational else " (paper does not look computational)"))

    req_stmt = [p for p in ex["on_request"] if any(p[:40] in s["text"] or s["text"][:60] in p for s in stmts)]
    if ex["on_request"]:
        add("not_on_request", "No 'available on request'", FAIL if (req_stmt or not data_links) else WARN,
            ex["on_request"][0][:200])
    else:
        add("not_on_request", "No 'available on request'", PASS, "")
    if ex["future_release"]:
        add("not_future", "No 'will be made available'", FAIL, ex["future_release"][0][:200])

    alive_code = [l for l in code_links if l["alive"] is not False]
    if code_links:
        add("code_link", "Code link present", PASS if alive_code else FAIL,
            ", ".join(l["url"] for l in code_links[:4]))
    else:
        add("code_link", "Code link present", FAIL if computational else NA, "no code repository link")

    dead = [l for l in links if l["alive"] is False]
    unknown = [l for l in links if l["alive"] is None]
    if not links:
        add("links_alive", "All links resolve", NA, "no links")
    elif dead:
        add("links_alive", "All links resolve", FAIL, "dead: " + ", ".join(f'{l["url"]} ({l["status"]})' for l in dead[:5]))
    elif unknown:
        add("links_alive", "All links resolve", WARN, "unverifiable (blocked/rate-limited): " + ", ".join(l["url"] for l in unknown[:5]))
    else:
        add("links_alive", "All links resolve", PASS, f"{len(links)} link(s) OK")

    if code_links or any(l["repo_type"] == "zenodo" and l["kind"] == "code" for l in links):
        archived = [l for l in links if l["archived_doi"] and (l["kind"] in ("code", "archive") or l.get("linked_github"))]
        if archived:
            add("code_archived", "Code archived with DOI", PASS, ", ".join(l["url"] for l in archived[:3]))
        else:
            add("code_archived", "Code archived with DOI", WARN, "only bare git-host links (no Zenodo/SWH snapshot)")
        gits = [l for l in code_links if l["repo_type"] in ("github", "gitlab") and l["alive"]]
        lic = [l for l in code_links + archived if l.get("license")]
        if gits or archived:
            add("code_license", "Code has a license", PASS if lic else FAIL,
                ", ".join(sorted({str(l["license"]) for l in lic})) or "no license detected")
        pinned = [l for l in code_links + archived if l.get("pinned_ref") or l.get("releases_before_pub") or l["archived_doi"]]
        drift = [l for l in gits if l.get("commits_after_pub")]
        if pinned:
            add("version_pinned", "Version/tag matching paper", PASS,
                "; ".join(f'{l["url"]}: {l.get("pinned_ref") or ", ".join(l.get("releases_before_pub") or []) or "archived"}' for l in pinned[:3]))
        else:
            add("version_pinned", "Version/tag matching paper", WARN,
                "no tag/release/commit tied to paper" + ("; repo changed after publication" if drift else ""))
    else:
        add("code_archived", "Code archived with DOI", NA, "")

    if repos:
        ok = [r for r in repos if r.get("checks")]
        if not ok:
            add("repo_checks", "Repo light checks", FAIL, "; ".join(r.get("error", "") for r in repos))
        else:
            fails = [f'{r["url"].split("/")[-1]}:{c["id"]}' for r in ok for c in r["checks"] if not c["passed"]]
            add("repo_checks", "Repo light checks", PASS if not fails else WARN, ("missing " + ", ".join(fails)) if fails else "deps, README run steps, entry point, license")

    if ex["no_data"] and not data_links:
        add("data_deposited", "Data deposited", NA, ex["no_data"][0][:200])
    elif data_links or ex["accessions"]:
        add("data_deposited", "Data deposited", PASS,
            ", ".join([l["url"] for l in data_links[:3]] + [a["id"] for a in ex["accessions"][:3]]))
    elif ex["data_in_paper"]:
        add("data_deposited", "Data deposited", WARN, "data said to be in paper/supplement only")
    elif ex["generated_data_terms"]:
        add("data_deposited", "Data deposited", FAIL,
            "methods mention " + ", ".join(ex["generated_data_terms"][:4]) + " but no repository/accession found")
    else:
        add("data_deposited", "Data deposited", WARN, "no data repository link or accession found")
    return items


def score(items: List[Item]) -> dict:
    app = [i for i in items if i.status != NA]
    pts = sum(1 if i.status == PASS else 0.5 if i.status == WARN else 0 for i in app)
    return {"score": round(100 * pts / len(app)) if app else 0,
            "pass": sum(i.status == PASS for i in items), "warn": sum(i.status == WARN for i in items),
            "fail": sum(i.status == FAIL for i in items)}


def audit(inp: str, clone: bool = True, paper: Optional[Paper] = None, log=lambda *_: None) -> dict:
    p = paper or load_paper(inp)
    log(f"text: {p.text_source}")
    ex = extract(p.text, p.full_text, p.pdf_links, p.doi)
    candidates = sorted(ex.links, key=lambda l: (not l.in_statement, l.kind not in ("code", "archive", "data")))
    links = []
    for l in candidates[:MAX_LINKS]:
        log(f"resolve {l.url}")
        links.append(resolve_link(l, p.published).to_dict())
    # dedupe repos that were linked via several URLs
    repos, seen = [], set()
    if clone:
        for l in links:
            if l.get("clone_url") and l["alive"] and l["repo"] not in seen and len(repos) < MAX_CLONES:
                seen.add(l["repo"])
                log(f"clone {l['clone_url']}")
                r = check_repo(l["clone_url"], l.get("pinned_ref"))
                r["url"] = l["final_url"] or l["url"]
                repos.append(r)
    pd = {k: v for k, v in asdict(p).items() if k not in ("text", "full_text", "pdf_links")}
    exd = ex.to_dict()
    exd.pop("links")
    items = build_checklist(pd, exd, links, repos)
    return {
        "tool": f"paper-repro-auditor {__version__}",
        "audited_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "paper": pd,
        "summary": score(items),
        "checklist": [asdict(i) for i in items],
        "evidence": {**exd, "links": links, "repos": repos},
    }
