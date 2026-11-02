"""Resolve links: alive? archived with DOI? license? version pinned relative to publication?"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from urllib.parse import quote, urlparse

from . import http
from .extract import Link


@dataclass
class LinkResult:
    url: str
    repo_type: str
    kind: str
    in_statement: bool
    status: int = 0
    alive: Optional[bool] = None     # None = unknown (blocked / rate-limited)
    final_url: str = ""
    archived_doi: bool = False       # persistent archive with DOI (Zenodo, Figshare, Dryad, ...)
    license: Optional[str] = None
    repo: Optional[str] = None       # owner/name for git hosts
    clone_url: Optional[str] = None
    pinned_ref: Optional[str] = None  # tag/commit/release referenced in the URL
    releases_before_pub: List[str] = field(default_factory=list)
    commits_after_pub: Optional[bool] = None
    archived_repo: Optional[bool] = None   # GitHub "archived" (read-only) flag
    linked_github: Optional[str] = None    # e.g. Zenodo record that mirrors a GitHub release
    stmt_kind: Optional[str] = None
    pre: str = ""
    stars: Optional[int] = None
    size_kb: Optional[int] = None
    third_party: bool = False              # cited tool/dependency rather than the paper's own code
    notes: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _plus_days(date: str, days: int) -> str:
    import datetime as dt
    try:
        d = dt.date.fromisoformat(date[:10]) if len(date) >= 10 else dt.date(int(date[:4]), 12, 31)
    except ValueError:
        return date
    return (d + dt.timedelta(days=days)).isoformat()


def _gh_headers() -> dict:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _alive(url: str, r: http.Resp) -> Optional[bool]:
    if r.ok or 300 <= r.status < 400:
        return True
    if r.status in (401, 403, 429, 999):
        return None
    if r.status == 0:   # DNS failure => dead host; timeouts/TLS/etc => unknown
        return False if re.search(r"NameResolution|Failed to resolve|nodename", r.error) else None
    return False


def check_http(res: LinkResult) -> None:
    r = http.request(res.url, browser=True, max_bytes=200_000, retry=False)
    res.status, res.final_url = r.status, r.url
    res.alive = _alive(res.url, r)
    if r.status == 0:
        res.notes.append(r.error)


GH_PATH = re.compile(r"^/([^/]+)/([^/#?]+)(?:/(tree|blob|releases/tag|commit|archive)/([^/#?]+))?")


def check_github(res: LinkResult, published: str) -> None:
    p = urlparse(res.url)
    m = GH_PATH.match(p.path)
    if not m or m.group(1) in ("orgs", "topics", "features", "about", "sponsors"):
        check_http(res)
        return
    owner, name = m.group(1), re.sub(r"\.git$", "", m.group(2))
    if m.group(3) and m.group(4) not in ("master", "main", "HEAD", "develop", "dev"):
        res.pinned_ref = m.group(4)
    if name in ("", "."):  # user/org page
        check_http(res)
        return
    api = f"https://api.github.com/repos/{owner}/{name}"
    r = http.request(api, headers=_gh_headers())
    res.status = r.status
    if r.status == 404:
        res.alive = False
        res.notes.append("GitHub repo not found (deleted, renamed or private)")
        return
    if not r.ok:
        res.alive = None
        res.notes.append(f"GitHub API {r.status} (set GITHUB_TOKEN to avoid rate limits)")
        return
    j = r.json()
    res.alive = True
    res.repo = j.get("full_name")
    res.final_url = j.get("html_url", "")
    res.clone_url = j.get("clone_url")
    res.license = ((j.get("license") or {}).get("spdx_id")) or None
    if res.license == "NOASSERTION":
        res.notes.append("license file present but not recognised by GitHub")
    res.archived_repo = j.get("archived")
    res.stars, res.size_kb = j.get("stargazers_count"), j.get("size")
    if published:
        rel = http.get_json(f"{api}/releases?per_page=100", headers=_gh_headers()) or []
        # releases up to 30 days after publication still count as "the paper's version"
        cutoff = _plus_days(published, 30)
        res.releases_before_pub = [x.get("tag_name") for x in rel
                                   if (x.get("published_at") or "9")[:10] <= cutoff][:10]
        if not rel:
            tags = http.get_json(f"{api}/tags?per_page=100", headers=_gh_headers()) or []
            if tags:
                res.notes.append(f"{len(tags)} git tag(s), no GitHub releases")
        c = http.request(f"{api}/commits?since={published[:10]}T00:00:00Z&per_page=1",
                         headers=_gh_headers())
        if c.ok:
            res.commits_after_pub = bool(c.json())


def check_gitlab(res: LinkResult) -> None:
    p = urlparse(res.url)
    path = p.path.strip("/").split("/-/")[0]
    if "/-/tree/" in p.path or "/-/tags/" in p.path:
        res.pinned_ref = p.path.rsplit("/", 1)[-1]
    j = http.get_json(f"https://gitlab.com/api/v4/projects/{quote(path, safe='')}?license=true")
    if not j:
        check_http(res)
        return
    res.alive, res.status = True, 200
    res.repo = j.get("path_with_namespace")
    res.clone_url = j.get("http_url_to_repo")
    res.license = (j.get("license") or {}).get("key")


def check_zenodo(res: LinkResult) -> None:
    m = re.search(r"zenodo\.(\d+)", res.url) or re.search(r"zenodo\.org/(?:records?|deposit)/(\d+)", res.url)
    if not m:
        check_http(res)
        return
    j = http.get_json(f"https://zenodo.org/api/records/{m.group(1)}")
    if not j:
        check_http(res)
        return
    res.alive, res.status, res.archived_doi = True, 200, True
    md = j.get("metadata") or {}
    lic = md.get("license") or {}
    res.license = lic.get("id") if isinstance(lic, dict) else lic
    res.pinned_ref = md.get("version") or f"zenodo:{m.group(1)}"
    rtype = (md.get("resource_type") or {}).get("type")
    if rtype == "software":
        res.kind = "code"
    elif rtype == "dataset":
        res.kind = "data"
    for ri in md.get("related_identifiers") or []:
        if "github.com" in (ri.get("identifier") or ""):
            res.linked_github = ri["identifier"]
            break


def check_figshare(res: LinkResult) -> None:
    m = re.search(r"figshare\.(\d+)", res.url) or re.search(r"figshare\.com/articles/(?:[^/]+/)*(\d+)", res.url)
    j = http.get_json(f"https://api.figshare.com/v2/articles/{m.group(1)}") if m else None
    if not j:
        check_http(res)
        res.archived_doi = res.alive is not False
        return
    res.alive, res.status, res.archived_doi = True, 200, True
    res.license = (j.get("license") or {}).get("name")
    res.pinned_ref = f"figshare:{m.group(1)} v{j.get('version', '?')}"
    t = (j.get("defined_type_name") or "").lower()
    if t == "software":
        res.kind = "code"
    elif t in ("dataset", "figure", "media", "fileset", "online resource"):
        res.kind = "data"


def check_doi(res: LinkResult) -> None:
    check_http(res)
    if res.repo_type not in ("doi", "other"):
        res.archived_doi = True
    elif res.final_url:
        host = urlparse(res.final_url).netloc.lower()
        for h, rt in (("zenodo", "zenodo"), ("figshare", "figshare"), ("datadryad", "dryad"),
                      ("osf.io", "osf"), ("dataverse", "dataverse"), ("pangaea", "pangaea"),
                      ("codeocean", "codeocean"), ("mendeley", "mendeley-data")):
            if h in host:
                res.archived_doi, res.repo_type = True, rt
                break


def resolve_link(link: Link, published: str = "") -> LinkResult:
    res = LinkResult(link.url, link.repo_type, link.kind, link.in_statement,
                     stmt_kind=link.stmt_kind, pre=link.pre)
    try:
        if link.repo_type == "github":
            check_github(res, published)
        elif link.repo_type == "gitlab":
            check_gitlab(res)
        elif link.repo_type == "zenodo":
            check_zenodo(res)
        elif link.repo_type == "figshare":
            check_figshare(res)
        elif link.host in ("doi.org", "dx.doi.org"):
            if link.repo_type == "zenodo":
                check_zenodo(res)
            else:
                check_doi(res)
        else:
            check_http(res)
            if link.repo_type in ("figshare", "osf", "dryad", "dataverse", "pangaea", "mendeley-data",
                                  "swh", "codeocean"):
                res.archived_doi = True   # these platforms mint DOIs/persistent ids
    except http.OfflineError:
        raise
    except Exception as e:  # noqa: BLE001 - one bad link must not abort the audit
        res.notes.append(f"resolver error: {e}")
    return res
