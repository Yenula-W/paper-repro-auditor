"""Orchestrate one audit and turn evidence into a checklist."""
from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import List, Optional

from . import __version__
from .extract import OWN_CUE, data_code_requests, extract, sentence_before
from .repocheck import check_repo
from .resolve import resolve_link
from .sources import Paper, load_paper

PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "N/A"
CODE_TYPES = {"github", "gitlab", "bitbucket", "codeocean", "swh", "sourceforge", "pypi", "cran", "bioconductor",
              "googlecode"}
MAX_LINKS = 30
MAX_CLONES = 2
NON_RESEARCH = {"review-article", "editorial", "correction", "news", "commentary", "article-commentary",
                "book-review", "obituary", "retraction", "expression-of-concern", "announcement", "in-brief"}
# not listed on purpose: "letter" (Nature Letters are research), "product-review" (BMC tags Software articles so)
CHECK_NAMES = {"dependency_file": "dependency file", "readme": "README", "readme_run_steps": "run instructions in README",
               "entry_point": "entry-point script", "license_file": "license file",
               "readme_scripts_exist": "scripts named in README"}
REGISTRY_TYPES = {"pypi", "cran", "bioconductor"}
# "TensorFlow v.1 (url)", "WRF v3.9.1.1 source code ... here: url", "developed with X (url)"
TOOL_CUE = re.compile(r"(?:\bv\.?\s?\d[\w.]*\)?|version\s+\d[\w.]*|developed\s+(?:with|using)|"
                      r"implemented\s+(?:in|with|using)|built\s+(?:with|on))(?!\w)[^()\n]{0,50}\(?\s*$"
                      # passive third-party use: "idock [33] (v2.1.3) was downloaded from (url)"
                      r"|\b(?:was|were)\s+(?:downloaded|obtained|installed|retrieved)\s+(?:from|at|via)\s*\(?\s*$", re.I)


@dataclass
class Item:
    id: str
    label: str
    status: str
    detail: str = ""


def _data_on_code_host(l: dict) -> bool:
    """'Sapflux data are archived in the sapfluxnet database (https://github.com/sapfluxnet/...)':
    a code host used for data, with no word about code in that sentence."""
    if not (l["in_statement"] and l["repo_type"] in ("github", "gitlab", "bitbucket")):
        return False
    sent = sentence_before(l.get("pre") or "")
    return bool(re.search(r"\bdata(?:sets?|base)?\b", sent, re.I)) and not CODE_WORDS.search(sent)


def _is_code(l: dict) -> bool:
    if l.get("third_party") or _data_on_code_host(l):
        return False
    if l["kind"] == "web":
        return False
    # archive of unknown type in a code statement, or "analysis codes ... can be found on <OSF>"
    return (l["repo_type"] in CODE_TYPES or l["kind"] == "code"
            or (l["kind"] == "archive" and l.get("stmt_kind") == "code")
            or (l["kind"] == "archive" and l["in_statement"] and bool(CODE_WORDS.search((l.get("pre") or "")[-160:]))))


LICENSE_TEXT = re.compile(r"\b(?:(?:new\s+|modified\s+|simplified\s+)?BSD|MIT|Apache|L?GPL(?:v?\d)?|"
                          r"GNU\s+(?:Lesser\s+|Affero\s+)?General\s+Public|CC[- ]BY(?:[- ]\w+)*|CC0|"
                          r"Creative\s+Commons|Mozilla\s+Public|Artistic)\b(?:[^.]{0,30}?licen[cs]e)?", re.I)
CODE_MENTION = re.compile(r"\b(?<!accession )(?<!access )(?<!postal )(?:(?:source\s+|analysis\s+|simulation\s+|computer\s+)?codes?|scripts?|"
                          r"jupyter\s+notebooks?|R\s+markdown)\b(?!\.\w)", re.I)   # not "diagnosis codes.csv"
SUPP_CODE = re.compile(r"\b(?:codes?|scripts?|notebooks?)\b[^.]{0,120}\b(?:supplement\w*|supporting\s+information|"
                       r"additional\s+files?|appendix)\b", re.I)
CODE_WORDS = re.compile(r"\b(?:codes?|scripts?|software|source)\b", re.I)
# analysis code listed as files of a data deposit: "analysis_v1.do (STATA script ...)" in a Dataverse record
CODE_FILES = re.compile(r"\b(?:[Ss]cripts?|[Nn]otebooks?|[Ss]ource\s+code|[Aa]nalysis\s+code|do-files?)\b|\w\.(?:do|R|Rmd|py|ipynb|jl)\b")
# "The article used no data as it is a literature review."
REVIEW_STMT = re.compile(r"\b(?:literature|systematic|narrative|scoping)\s+review\b|\b(?:is|as)\s+an?\s+(?:\w+\s+)?(?:review|survey)\b", re.I)


def _sentence_with(text: str, url: str) -> str:
    i = text.find(url)
    if i < 0:
        return ""
    end = text.find(". ", i + len(url))
    return text[text.rfind(". ", 0, i) + 1: end if end >= 0 else len(text)]


def _is_data(l: dict) -> bool:
    return not _is_code(l) and not l.get("third_party") and l["kind"] != "web" and (
        l["kind"] in ("data", "archive") or (l["in_statement"] and l["kind"] == "doi"))


def _code_only_request(snippet: str) -> bool:
    """'Model source code is available upon request' says nothing about the data."""
    sent = re.split(r"(?<=[.;])\s+", snippet[:snippet.lower().rfind("request") + 7])[-1]
    return bool(CODE_WORDS.search(sent)) and not re.search(r"\bdata(?:sets?)?\b", sent, re.I)


def _why(l: dict) -> str:
    if l["status"]:
        return f"HTTP {l['status']}"
    return "host name no longer resolves"


NOT_REPO = re.compile(r"/(?:issues|pull|discussions|wiki|blob/[^/]+/[^/]+\.(?:md|txt))(?:/|$)", re.I)


_sentence = sentence_before


def _owner(l: dict) -> Optional[str]:
    m = re.match(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/([^/]+)", l["url"], re.I)
    return m.group(1).lower() if m else None


def _named_in_title(l: dict, title: str) -> bool:
    """Tool papers: 'FLaapLUC: a pipeline ...' links github.com/jlenain/flaapluc."""
    m = re.match(r"https?://[^/]+/[^/]+/([^/#?]+)", l["url"])
    # "DrWatson: the perfect sidekick ..." owns github.com/JuliaDynamics/DrWatson.jl
    name = re.sub(r"\.(?:git|jl|py|r|js|rs)$", "", (m.group(1) if m else "").lower())
    name = re.sub(r"[^a-z0-9]", "", name)
    return len(name) >= 4 and name in re.sub(r"[^a-z0-9]", "", (title or "").lower())


def mark_third_party(links: List[dict], title: str = "") -> None:
    """Heuristically flag links to cited tools/dependencies (not the paper's own code).

    A code link counts as the authors' own when it is in an availability statement (and not
    phrased as a versioned tool citation), when the text before it says it is available/ours,
    or when it shares a git owner with such a link. Everything else (tool tables, issue
    trackers, 'we used X (url)') is a cited tool.
    """
    first_own = True
    own_owners = set()
    for l in links:
        if l["repo_type"] not in CODE_TYPES:
            continue
        pre = l.get("pre") or ""
        if TOOL_CUE.search(pre[-80:]):
            l["third_party"] = True
        elif l["repo_type"] in REGISTRY_TYPES and not l["in_statement"]:
            l["third_party"] = True
        elif NOT_REPO.search(l["url"]):
            l["third_party"] = True
        elif not l["in_statement"] and not OWN_CUE.search(_sentence(pre[-160:])) and not _named_in_title(l, title):
            l["third_party"] = True
            l["unclaimed"] = True        # no cue either way: could still be the authors' code
        elif not first_own and (l.get("stars") or 0) >= 5000:
            l["third_party"] = True
        if not l.get("third_party"):
            first_own = False
            if _owner(l):
                own_owners.add(_owner(l))
    for l in links:   # e.g. FlyBrainLab/Tutorials next to FlyBrainLab/FlyBrainLab
        if l.get("third_party") and _owner(l) in own_owners and not NOT_REPO.search(l["url"]) \
                and not TOOL_CUE.search((l.get("pre") or "")[-80:]):
            l["third_party"] = False


def build_checklist(paper: dict, ex: dict, links: List[dict], repos: List[dict]) -> List[Item]:
    items: List[Item] = []
    add = lambda *a: items.append(Item(*a))  # noqa: E731
    if paper["text_source"] == "none":
        if paper.get("is_oa"):   # the paper is open; the publisher just blocks automated downloads
            add("full_text", "Full text retrieved", WARN,
                "the paper is listed as open access, but no full text could be downloaded automatically "
                "(the publisher may block automated downloads); audit a saved PDF instead: paper-audit paper.pdf")
        else:
            add("full_text", "Full text retrieved", FAIL, "; ".join(paper["warnings"]) or "no open-access text")
        return items
    add("full_text", "Full text retrieved", PASS, paper["text_source"])
    atype = (paper.get("article_type") or "").lower()
    if atype in NON_RESEARCH:
        for cid, label in (("data_statement", "Data availability statement"),
                           ("code_statement", "Code availability statement"),
                           ("data_deposited", "Data deposited")):
            add(cid, label, NA, f"not expected for this article type ({atype})")
        return items

    stmts = ex["statements"]
    data_st = [s for s in stmts if s["kind"] in ("data", "both")]
    # a combined "Data and code availability" section only counts for code if it talks about code
    code_st = [s for s in stmts if s["kind"] == "code"
               or (s["kind"] == "both" and CODE_WORDS.search(s["text"]))
               or (s["kind"] == "data" and CODE_MENTION.search(s["text"]))]   # "data and scripts are ..."
    supp_code = [s for s in code_st if SUPP_CODE.search(s["text"])]
    computational = ex["computational_hits"] >= 3 or any(
        CODE_MENTION.search(s["text"]) for s in stmts)
    if ex["no_data"] and any(REVIEW_STMT.search(s["text"]) for s in data_st):
        computational = False   # a literature review that states it used no data needs no code either
    code_links = [l for l in links if _is_code(l)]
    # a DOI archive (Dataverse, Zenodo dataset ...) whose statement lists analysis scripts holds code too
    code_links += [l for l in links if l not in code_links and l["in_statement"] and l["archived_doi"]
                   and not l.get("third_party") and l["kind"] in ("data", "archive", "doi")
                   and any(l["url"].split("doi.org/")[-1] in st["text"] and CODE_FILES.search(st["text"]) for st in stmts)]
    cited = [l for l in links if l.get("third_party")]
    unclaimed = [l for l in cited if l.get("unclaimed") and l["alive"] is not False]
    web_own = [l for l in links if l["kind"] == "web" and l.get("own_web") and l["alive"] is not False]
    code_req = [s for s in code_st if data_code_requests(s["text"])]
    data_links = [l for l in links if _is_data(l)]
    code_in_stmt = [l for l in code_links if l["in_statement"]]

    add("data_statement", "Data availability statement", PASS if data_st else FAIL,
        data_st[0]["text"][:200] if data_st else "no data availability statement found in the full text")

    if code_st:
        add("code_statement", "Code availability statement", PASS, code_st[0]["text"][:200])
    elif code_in_stmt:
        add("code_statement", "Code availability statement", PASS, "code link given in availability statement")
    elif code_links:
        add("code_statement", "Code availability statement", WARN, "no dedicated statement; code linked in body text")
    elif any(s["kind"] == "both" for s in stmts):
        add("code_statement", "Code availability statement", WARN if computational else NA,
            "a combined data/code availability section is present but does not mention code")
    else:
        add("code_statement", "Code availability statement", FAIL if computational else NA,
            "no code availability statement found" + ("" if computational else " (the paper does not appear to rely on custom code)"))

    req_stmt = [p for p in ex["on_request"] if any(p[:40] in s["text"] or s["text"][:60] in p for s in stmts)]
    if ex["on_request"]:
        add("not_on_request", "No 'available on request'", FAIL if (req_stmt or not data_links) else WARN,
            ex["on_request"][0][:200])
    else:
        add("not_on_request", "No 'available on request'", PASS, "")
    if ex["future_release"]:
        add("not_future", "No 'will be made available'", FAIL, ex["future_release"][0][:200])

    alive_code = [l for l in code_links if l["alive"] is not False]
    cited_note = f" ({len(cited)} cited third-party tool link(s) ignored)" if cited else ""
    if code_links:
        add("code_link", "Code link present", PASS if alive_code else FAIL,
            ", ".join(l["url"] for l in code_links[:4]))
    elif code_req:
        add("code_link", "Code link present", FAIL, "code only 'available on request'" + cited_note)
    elif supp_code:
        add("code_link", "Code link present", WARN,
            "code is provided as supplementary material only (no repository or archive with a DOI)")
    elif code_st:
        add("code_link", "Code link present", WARN,
            "code statement gives no source repository (web service / description only)" + cited_note)
    elif web_own:
        add("code_link", "Code link present", WARN if computational else NA,
            "only a web service / project page is linked (" + ", ".join(l["url"] for l in web_own[:2])
            + "); no source-code repository found")
    elif unclaimed and computational:
        add("code_link", "Code link present", WARN,
            "code-host links found, but none is clearly identified as the authors' code: "
            + ", ".join(l["url"] for l in unclaimed[:3]) + " (please check)")
    else:
        add("code_link", "Code link present", FAIL if computational else NA, "no link to the authors' own code found" + cited_note)

    dead = [l for l in links if l["alive"] is False]
    unknown = [l for l in links if l["alive"] is None]
    if not links:
        add("links_alive", "All links resolve", NA, "no links")
    elif dead:
        add("links_alive", "All links resolve", FAIL, "not reachable when checked: " + ", ".join(f'{l["url"]} ({_why(l)})' for l in dead[:5]))
    elif unknown:
        add("links_alive", "All links resolve", WARN, "could not be verified automatically (site blocks automated requests or timed out): " + ", ".join(l["url"] for l in unknown[:5]))
    else:
        add("links_alive", "All links resolve", PASS, f"{len(links)} link(s) OK")

    if code_links:
        archived = [l for l in code_links if l["archived_doi"] or l.get("linked_github")]
        if archived:
            add("code_archived", "Code archived with DOI", PASS, ", ".join(l["url"] for l in archived[:3]))
        else:
            add("code_archived", "Code archived with DOI", WARN, "code is linked only on a code-hosting site; no archived snapshot with a DOI (e.g. Zenodo, Software Heritage) was found")
        gits = [l for l in code_links if l["repo_type"] in ("github", "gitlab") and l["alive"]]
        lic = [l for l in code_links + archived if l.get("license")]
        lic_text = sorted({m.group(0).strip() for st in code_st for m in LICENSE_TEXT.finditer(st["text"])})
        if gits or archived or code_links:
            found_lic = sorted({str(l["license"]) for l in lic}) + [f'"{t}" (stated in paper)' for t in lic_text]
            if found_lic:
                add("code_license", "Code has a license", PASS, ", ".join(found_lic))
            elif gits or archived:
                add("code_license", "Code has a license", FAIL, "no license found on the linked repository or archive")
            elif not alive_code or all(l["alive"] is False for l in code_links if l["repo_type"] in ("github", "gitlab")):
                add("code_license", "Code has a license", WARN,
                    "license could not be checked: the code repository was not reachable")
            else:
                add("code_license", "Code has a license", WARN,
                    "license could not be checked automatically for this host and none is stated in the paper")
        pinned = list({l["url"]: l for l in code_links + archived
                       if l.get("pinned_ref") or l.get("releases_before_pub") or l["archived_doi"]}.values())
        drift = [l for l in gits if l.get("commits_after_pub")]
        if pinned:
            add("version_pinned", "Version/tag matching paper", PASS,
                "; ".join(f'{l["url"]}: {l.get("pinned_ref") or ", ".join(l.get("releases_before_pub") or []) or "archived"}' for l in pinned[:3]))
        else:
            add("version_pinned", "Version/tag matching paper", WARN,
                "no release, tag or commit identifying the version used in the paper" + ("; the repository has changed since publication" if drift else ""))
    else:
        add("code_archived", "Code archived with DOI", NA, "")

    if repos:
        ok = [r for r in repos if r.get("checks")]
        if not ok:
            add("repo_checks", "Repo light checks", FAIL, "; ".join(r.get("error", "") for r in repos))
        else:
            fails = [f'{r["url"].split("/")[-1]}: {CHECK_NAMES.get(c["id"], c["id"])}' for r in ok for c in r["checks"] if not c["passed"]]
            add("repo_checks", "Repo light checks", PASS if not fails else WARN, ("not found: " + ", ".join(fails)) if fails else "dependency file, README run steps, entry point and license present")

    data_req = [st for st in data_st if any(not _code_only_request(r) for r in data_code_requests(st["text"]))]
    # data-type terms only ("RNA-seq", "questionnaire"); verbs alone ("we measured") prove nothing
    data_terms = [t for t in ex["generated_data_terms"] if not t.startswith("we ") and "participants" not in t]
    # "All data and scripts ... are available at <github/swh>" => data deposited with the code
    # the sentence holding the link must mention data ("The NACC code is available at <zenodo>" does not)
    data_in_code = [l for l in code_links if l.get("stmt_kind") in ("data", "both")
                    and any(re.search(r"\bdata(?:sets?)?\b", _sentence_with(st["text"], l["url"]), re.I) for st in data_st)]
    # "Samples of our datasets are available at <github>": data on a code host, without an archive
    data_in_code += [l for l in links if _data_on_code_host(l) and not l.get("third_party") and l not in data_in_code]
    if data_req and not data_links and not ex["accessions"] and not data_in_code:
        add("data_deposited", "Data deposited", FAIL, "data only 'available on request'")
    elif ex["no_data"] and not data_links:
        add("data_deposited", "Data deposited", NA, ex["no_data"][0][:200])
    elif data_links or ex["accessions"]:
        add("data_deposited", "Data deposited", PASS,
            ", ".join([l["url"] for l in data_links[:3]] + [a["id"] for a in ex["accessions"][:3]]))
    elif data_in_code:
        arch = [l for l in data_in_code if l["archived_doi"] or l["repo_type"] == "swh"]
        add("data_deposited", "Data deposited", PASS if arch else WARN,
            ("data shipped with archived code: " if arch else "data only in a git repository (no DOI archive): ")
            + ", ".join(l["url"] for l in (arch or data_in_code)[:3])
            + ("; other data only 'available on request'" if data_req else ""))
    elif ex["data_in_paper"]:
        add("data_deposited", "Data deposited", WARN, "data are stated to be in the paper/supplement only; no repository deposit found")
    elif data_terms and ex.get("generated_data_verbs"):
        add("data_deposited", "Data deposited", FAIL,
            "methods mention " + ", ".join(data_terms[:4]) + " but no repository link or accession number was found")
    else:
        add("data_deposited", "Data deposited", WARN, "no data repository link or accession number found")
    return items


def score(items: List[Item]) -> dict:
    app = [i for i in items if i.status != NA]
    pts = sum(1 if i.status == PASS else 0.5 if i.status == WARN else 0 for i in app)
    return {"score": round(100 * pts / len(app)) if app else 0,
            "pass": sum(i.status == PASS for i in items), "warn": sum(i.status == WARN for i in items),
            "fail": sum(i.status == FAIL for i in items)}


# Checks that missed the shipping precision bar on untouched rounds (see EVALUATION.md): off by
# default, enabled with --experimental. Their evidence (accessions, data links) is always reported.
EXPERIMENTAL = {"data_deposited", "not_future"}


def audit(inp: str, clone: bool = True, paper: Optional[Paper] = None, log=lambda *_: None,
          experimental: bool = False) -> dict:
    p = paper or load_paper(inp)
    log(f"text: {p.text_source}")
    ex = extract(p.text, p.full_text, p.pdf_links, p.doi)
    candidates = sorted(ex.links, key=lambda l: (not l.in_statement, l.kind not in ("code", "archive", "data")))
    log(f"resolving {min(len(candidates), MAX_LINKS)} link(s)")
    with ThreadPoolExecutor(max_workers=8) as pool:
        links = [r.to_dict() for r in pool.map(lambda l: resolve_link(l, p.published), candidates[:MAX_LINKS])]
    mark_third_party(links, p.title)
    # dedupe repos that were linked via several URLs
    repos, seen = [], set()
    if clone:
        for l in links:
            if (l.get("clone_url") and l["alive"] and not l.get("third_party")
                    and l["repo"] not in seen and len(repos) < MAX_CLONES):
                seen.add(l["repo"])
                log(f"clone {l['clone_url']}")
                r = check_repo(l["clone_url"], l.get("pinned_ref"))
                r["url"] = l["final_url"] or l["url"]
                repos.append(r)
    pd = {k: v for k, v in asdict(p).items() if k not in ("text", "full_text", "pdf_links")}
    exd = ex.to_dict()
    exd.pop("links")
    items = build_checklist(pd, exd, links, repos)
    if not experimental:
        items = [i for i in items if i.id not in EXPERIMENTAL]
    return {
        "tool": f"paper-repro-auditor {__version__}",
        "audited_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "paper": pd,
        "summary": score(items),
        "experimental_checks": experimental,
        "checklist": [asdict(i) for i in items],
        "evidence": {**exd, "links": links, "repos": repos},
    }
