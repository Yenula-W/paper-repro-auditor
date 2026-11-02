"""Find availability statements, links, accessions and red-flag phrases in paper text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------- statements

HEADINGS = [
    # (regex, kind)
    (r"data\s+and\s+(?:code|software)\s+availability", "both"),
    (r"(?:code|software)\s+and\s+data\s+availability", "both"),
    (r"availability\s+of\s+data\s+and\s+materials?", "data"),
    (r"availability\s+of\s+data\s+and\s+code", "both"),
    (r"availability\s+and\s+implementation", "code"),
    (r"(?:code|software)\s+availability(?:\s+statement)?", "code"),
    (r"data\s+availability(?:\s+statement)?", "data"),
    (r"data\s+accessibility(?:\s+statement)?", "data"),
    (r"data\s+deposition", "data"),
    (r"resource\s+availability", "both"),
    (r"data,?\s+materials,?\s+and\s+software\s+availability", "both"),
    (r"open\s+(?:research|data)\s+statement", "data"),
    (r"data\s+records", "data"),
    (r"lead\s+contact\s+and\s+materials\s+availability", "both"),
]
STOP = re.compile(
    r"\n\s*(?:##\s*)?(?:references|acknowledg|author\s+contributions?|competing\s+interests?|"
    r"conflicts?\s+of\s+interest|declaration|funding|ethics|additional\s+information|"
    r"supplementary\s+(?:information|material)|correspondence|publisher'?s\s+note|"
    r"code\s+availability|data\s+availability|reporting\s+summary|extended\s+data|"
    r"financial\s+disclosure|abbreviations|consent|orcid|keywords?)\b",
    re.I,
)


@dataclass
class Statement:
    kind: str          # data | code | both
    heading: str
    text: str


def find_statements(text: str, max_len: int = 1500) -> List[Statement]:
    structured = "\n## " in text   # JATS-derived text keeps section titles as '## '
    out: List[Statement] = []
    seen_spans = []
    for pat, kind in HEADINGS:
        # heading at line start (optionally '## '), followed by ':' / newline / space
        rx = re.compile(r"(?:^|\n)[ \t]*(?:##\s*)?(" + pat + r")\s*[:.\-–—]?\s*", re.I)
        for m in rx.finditer(text):
            start = m.end()
            if any(a <= m.start(1) < b for a, b in seen_spans):
                continue
            body = text[start:start + max_len]
            # stop at the next known heading (but not immediately)
            s = STOP.search(body, 20)
            if s:
                body = body[: s.start()]
            if structured:
                para = body.split("\n## ", 1)[0]
            else:  # PDFs: a blank line usually ends the statement
                para = re.split(r"\n\s*\n(?!\s*(?:<|https?://))", body, 1)[0] if "\n\n" in body[40:] else body
            para = " ".join(para.split())
            if len(para) < 15:
                continue
            # skip table-of-contents / in-text mentions ("see Data availability")
            seen_spans.append((m.start(1), start + len(body)))
            out.append(Statement(kind, " ".join(m.group(1).split()), para))
    return out


# ---------------------------------------------------------------- links

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'\]\)}]+(?:\([^\s)]*\))?[^\s<>\"'\]\)}.,;:]*", re.I)
BARE_HOST_RE = re.compile(
    r"(?<![/\w.@])((?:github\.com|gitlab\.com|bitbucket\.org|zenodo\.org|osf\.io|figshare\.com|"
    r"datadryad\.org|codeocean\.com|huggingface\.co)/[^\s<>\"'\]\)}]+)", re.I)
DOI_TXT_RE = re.compile(r"(?<![\w/])(?:doi:\s*)?(10\.\d{4,9}/[^\s\"<>\]\)}]+)", re.I)

# DOI prefixes of archives/repositories
REPO_DOI_PREFIX = {
    "10.5281": "zenodo", "10.6084": "figshare", "10.5061": "dryad", "10.17605": "osf",
    "10.7910": "dataverse", "10.24433": "codeocean", "10.5066": "usgs", "10.1594": "pangaea",
    "10.17632": "mendeley-data", "10.15468": "gbif", "10.25740": "stanford-sdr",
    "10.6075": "ucsd-library", "10.4121": "4tu", "10.17863": "cambridge-repo",
    "10.5255": "uk-data-archive", "10.3886": "icpsr", "10.18150": "harvard-repo",
    "10.7272": "nimh-data", "10.26093": "university-repo", "10.57745": "recherche-data-gouv",
}

HOSTS = {
    "github.com": ("github", "code"), "gitlab.com": ("gitlab", "code"),
    "bitbucket.org": ("bitbucket", "code"), "codeocean.com": ("codeocean", "code"),
    "softwareheritage.org": ("swh", "code"), "archive.softwareheritage.org": ("swh", "code"),
    "sourceforge.net": ("sourceforge", "code"), "pypi.org": ("pypi", "code"),
    "cran.r-project.org": ("cran", "code"), "bioconductor.org": ("bioconductor", "code"),
    "zenodo.org": ("zenodo", "archive"), "figshare.com": ("figshare", "archive"),
    "osf.io": ("osf", "archive"), "datadryad.org": ("dryad", "data"),
    "dataverse.harvard.edu": ("dataverse", "data"), "data.mendeley.com": ("mendeley-data", "data"),
    "huggingface.co": ("huggingface", "data"), "kaggle.com": ("kaggle", "data"),
    "ncbi.nlm.nih.gov": ("ncbi", "data"), "ebi.ac.uk": ("ebi", "data"),
    "pangaea.de": ("pangaea", "data"), "openneuro.org": ("openneuro", "data"),
    "rcsb.org": ("pdb", "data"), "proteomecentral.proteomexchange.org": ("proteomexchange", "data"),
    "gbif.org": ("gbif", "data"), "physionet.org": ("physionet", "data"),
    "synapse.org": ("synapse", "data"), "icpsr.umich.edu": ("icpsr", "data"),
    "drive.google.com": ("google-drive", "data"), "dropbox.com": ("dropbox", "data"),
}

ACCESSION_RES = [
    (re.compile(r"\bGSE\d{3,8}\b"), "GEO"),
    (re.compile(r"\b(?:PRJNA|PRJEB|PRJDB)\d{3,8}\b"), "BioProject"),
    (re.compile(r"\b(?:SRP|SRR|SRX|ERP|ERR|DRP)\d{5,9}\b"), "SRA/ENA"),
    (re.compile(r"\bE-[A-Z]{4}-\d{2,6}\b"), "ArrayExpress"),
    (re.compile(r"\bPXD\d{6}\b"), "PRIDE"),
    (re.compile(r"\bEGA[SD]\d{11}\b"), "EGA"),
    (re.compile(r"\bphs\d{6}\b"), "dbGaP"),
    (re.compile(r"\bEMPIAR-\d{5}\b"), "EMPIAR"),
    (re.compile(r"\bEMD-\d{4,5}\b"), "EMDB"),
    (re.compile(r"\bMSV\d{9}\b"), "MassIVE"),
    (re.compile(r"\bds\d{6}\b"), "OpenNeuro"),
    (re.compile(r"\bCRA\d{6}\b"), "GSA"),
]


@dataclass
class Link:
    url: str
    host: str
    kind: str              # code | data | archive | doi | other
    repo_type: str          # github | zenodo | ...
    in_statement: bool = False
    context: str = ""
    stmt_kind: Optional[str] = None   # kind of the availability statement it appeared in
    pre: str = ""                      # ~60 chars of text before the link (for 'v1.2 (url)' cues)


def _clean_url(u: str) -> str:
    u = u.strip().rstrip(".,;:'\"")
    while u.endswith(")") and u.count("(") < u.count(")"):
        u = u[:-1]
    u = u.rstrip(".,;:")
    if u.lower().startswith("www."):
        u = "http://" + u
    return u


def classify_url(url: str) -> tuple[str, str, str]:
    """Return (host, kind, repo_type) for a URL."""
    p = urlparse(url)
    host = (p.netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if host in ("doi.org", "dx.doi.org"):
        doi = p.path.lstrip("/")
        pref = doi.split("/")[0]
        if pref in REPO_DOI_PREFIX:
            rt = REPO_DOI_PREFIX[pref]
            return host, ("code" if rt == "codeocean" else "archive" if rt in ("zenodo", "figshare", "osf") else "data"), rt
        return host, "doi", "doi"
    for h, (rt, kind) in HOSTS.items():
        if host == h or host.endswith("." + h):
            return host, kind, rt
    if host.endswith("figshare.com"):
        return host, "archive", "figshare"
    if "dataverse" in host:
        return host, "data", "dataverse"
    return host, "other", "other"


def _context(text: str, i: int, j: int, w: int = 120) -> str:
    return " ".join(text[max(0, i - w): j + w].split())


def _fix_pdf_breaks(text: str) -> str:
    """Re-join URLs broken across PDF line wraps (e.g. 'github.com/user/\\nrepo')."""
    return re.sub(r"((?:https?://|github\.com/|zenodo\.org/|doi\.org/)\S*[/\-_.=])\n(?=[\w\-])", r"\1", text)


def find_links(body: str, statements: List[Statement], extra: Optional[List[str]] = None,
               self_doi: Optional[str] = None) -> List[Link]:
    """Links worth auditing: everything in statements, plus repository-type links in the body."""
    found: dict = {}

    def add(url: str, in_stmt, ctx: str, pre: str = ""):
        url = _clean_url(url)
        if len(url) < 12:
            return
        host, kind, rt = classify_url(url)
        key = url.lower().rstrip("/")
        if self_doi and self_doi.lower() in key:
            return
        if key.endswith((".pdf",)) and kind == "other":
            return
        if key in found:
            if in_stmt and not found[key].in_statement:
                found[key].in_statement, found[key].stmt_kind = True, in_stmt
                found[key].pre = pre
            return
        found[key] = Link(url, host, kind, rt, bool(in_stmt), ctx, in_stmt or None, pre)

    srcs = [(s.text, s.kind) for s in statements] + [(_fix_pdf_breaks(body), None)]
    for src, in_stmt in srcs:
        hits = []
        for m in URL_RE.finditer(src):
            host, kind, _ = classify_url(_clean_url(m.group(0)))
            if in_stmt or kind != "other" and kind != "doi":
                hits.append((m.start(), m.end(), m.group(0)))
        for m in BARE_HOST_RE.finditer(src):
            hits.append((m.start(), m.end(), "https://" + m.group(1)))
        for m in DOI_TXT_RE.finditer(src):
            doi = _clean_url(m.group(1))
            if in_stmt or doi.split("/")[0] in REPO_DOI_PREFIX:
                hits.append((m.start(), m.end(), "https://doi.org/" + doi))
        for i, j, u in sorted(hits):   # keep reading order
            add(u, in_stmt, _context(src, i, j), " ".join(src[max(0, i - 60):i].split()))
    stmt_text = "\n".join(s.text for s in statements)
    for u in extra or []:
        host, kind, _ = classify_url(_clean_url(u))
        if kind not in ("other", "doi"):
            add(u, None, "")
    # Collapse URLs that are doi.org/X duplicates of https://doi.org/X variants
    return list(found.values())


def find_accessions(text: str) -> List[dict]:
    out, seen = [], set()
    for rx, db in ACCESSION_RES:
        for m in rx.finditer(text):
            if m.group(0) not in seen:
                seen.add(m.group(0))
                out.append({"id": m.group(0), "db": db})
    return out


# ---------------------------------------------------------------- flags

ON_REQUEST = re.compile(
    r"(?:available|provided|obtained|shared|accessible|supplied|made\s+available)\s+"
    r"(?:\w+\s+){0,6}?(?:up)?on\s+(?:\w+\s+){0,2}request"
    r"|(?:up)?on\s+(?:reasonable\s+)?request\s+(?:from|to)\s+the\s+(?:corresponding\s+)?authors?"
    r"|(?:contact|request(?:ed)?\s+from)\s+the\s+corresponding\s+author",
    re.I)
FUTURE = re.compile(r"will\s+be\s+(?:made\s+)?(?:publicly\s+)?(?:available|released|deposited|shared)"
                    r"|(?:up)?on\s+(?:acceptance|publication)|coming\s+soon", re.I)
IN_PAPER = re.compile(
    r"(?:all\s+)?(?:relevant\s+)?data\s+(?:are|is|were)\s+(?:included|available|provided|contained|presented)\s+"
    r"(?:\w+\s+){0,3}(?:in|within)\s+the\s+(?:paper|article|manuscript|main\s+text|supplement\w*|supporting)",
    re.I)
NO_DATA = re.compile(r"no\s+(?:new\s+)?data\s+(?:were|was)\s+(?:generated|created|used)|"
                     r"data\s+sharing\s+(?:is\s+)?not\s+applicable", re.I)

COMPUTATIONAL = re.compile(
    r"\b(?:python|matlab|r\s+package|rstudio|r\s+version|scikit-learn|pytorch|tensorflow|"
    r"custom\s+(?:code|script|software)|scripts?\s+(?:used|written)|we\s+(?:implemented|trained)|"
    r"simulations?|machine\s+learning|deep\s+learning|neural\s+network|github|source\s+code|"
    r"bioinformatic|pipeline|algorithm|numerical(?:ly)?|monte\s+carlo|regression\s+model|"
    r"R\s+Core\s+Team|lme4|GLMMs?|mixed[- ]effects?\s+models?|generali[sz]ed\s+linear|"
    r"GPU|convolutional|stochastic\s+gradient|train(?:ed|ing)\s+(?:on|with|set|data))\w*\b",
    re.I)
GENERATED_DATA = re.compile(
    r"\b(?:rna-?seq|scrna-?seq|single-cell\s+rna|whole[- ]genome\s+sequencing|exome\s+sequencing|"
    r"chip-?seq|atac-?seq|16s\s+rrna|metagenom\w*|sequencing\s+data|raw\s+reads|"
    r"mass\s+spectrometry|proteomic\w*|cryo-?em|crystal\s+structure|microarray|"
    r"we\s+(?:collected|recorded|generated|acquired|surveyed|measured)|"
    r"participants\s+were\s+recruited|questionnaire|field\s+(?:data|survey|sampling))\b",
    re.I)


GEN_VERBS = re.compile(r"\bwe\s+(?:collected|recorded|generated|acquired|sequenced|surveyed|measured|"
                       r"recruited|interviewed|sampled)\b|participants\s+were\s+recruited", re.I)


def find_phrases(rx: re.Pattern, text: str, limit: int = 5) -> List[str]:
    return [_context(text, m.start(), m.end(), 80) for m in list(rx.finditer(text))[:limit]]


@dataclass
class Extraction:
    statements: List[Statement] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    accessions: List[dict] = field(default_factory=list)
    on_request: List[str] = field(default_factory=list)
    future_release: List[str] = field(default_factory=list)
    data_in_paper: List[str] = field(default_factory=list)
    no_data: List[str] = field(default_factory=list)
    computational_hits: int = 0
    generated_data_terms: List[str] = field(default_factory=list)
    generated_data_verbs: List[str] = field(default_factory=list)   # "we collected/sequenced/..."

    def to_dict(self):
        return asdict(self)


def extract(body: str, full: str, extra_links=None, self_doi=None) -> Extraction:
    full = full or body
    stmts = find_statements(full)
    stmt_text = "\n".join(s.text for s in stmts)
    scope = stmt_text + "\n" + body
    gen = sorted({m.group(0).lower() for m in GENERATED_DATA.finditer(body)})
    return Extraction(
        statements=stmts,
        links=find_links(body, stmts, extra_links, self_doi),
        accessions=find_accessions(scope),
        on_request=find_phrases(ON_REQUEST, scope),
        future_release=find_phrases(FUTURE, stmt_text),
        data_in_paper=find_phrases(IN_PAPER, stmt_text),
        no_data=find_phrases(NO_DATA, stmt_text),
        computational_hits=len(COMPUTATIONAL.findall(body)),
        generated_data_terms=gen,
        generated_data_verbs=find_phrases(GEN_VERBS, body, 3),
    )
