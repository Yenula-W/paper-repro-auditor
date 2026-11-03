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
    (r"data,?\s+(?:and\s+)?materials\s+availability", "both"),   # Science family
    (r"availability\s+and\s+requirements", "code"),               # BMC software articles
    (r"data\s+sharing(?:\s+statement)?", "data"),                   # Lancet, BMJ
    (r"software(?=\s*\n)", "code"),          # a section titled just "Software"
    (r"lead\s+contact\s+and\s+materials\s+availability", "both"),
]
STOP = re.compile(
    r"\n\s*(?:##\s*)?(?:references|acknowledg|author\s+contributions?|competing\s+interests?|"
    r"conflicts?\s+of\s+interest|declaration|funding|ethics|additional\s+information|"
    r"supplementary\s+(?:information|material)|correspondence|publisher'?s\s+note|"
    r"code\s+availability|data\s+availability|reporting\s+summary|"
    # Nature "Extended Data" figures end a statement; F1000/Wellcome "Extended data Zenodo: ..." is part of it
    r"extended\s+data(?!\s+[A-Z][\w ]{0,40}:)|"
    r"financial\s+disclosure|abbreviations|consent|orcid|keywords?)\b",
    re.I,
)


@dataclass
class Statement:
    kind: str          # data | code | both
    heading: str
    text: str


def find_statements(text: str, max_len: int = 2500) -> List[Statement]:
    structured = "\n## " in text   # JATS-derived text keeps section titles as '## '
    out: List[Statement] = []
    seen_spans = []
    for pat, kind in HEADINGS:
        pat = pat.replace(r"\s+", r"\s*")   # PDF text can lose the spaces: "Dataavailabilitystatement" (IOP)
        # heading at line start (optionally '## '), followed by ':' / newline / space
        # heading on its own line, or a run-in head after a sentence ("... interests. Data and
        # materials availability: All data ...", as in Science journals) which must end in ':'
        # Copernicus numbers its sections: "6 Code and data availability"
        rx = re.compile(r"(?:(?:^|\n)[ \t]*(?:##\s*)?(?:\d{1,2}(?:\.\d{1,2})*\.?[ \t]+)?(" + pat + r")\s*[:.\-–—]?\s*"
                        r"|(?<=[.!?] )(" + pat + r")\s*:\s*)", re.I)
        for m in rx.finditer(text):
            start = m.end()
            g = 1 if m.group(1) else 2
            if any(a <= m.start(g) < b for a, b in seen_spans):
                continue
            body = text[start:start + max_len]
            # stop at the next known heading (but not immediately)
            s = STOP.search(body, 20)
            if s:
                body = body[: s.start()]
            if structured:
                raw = body.split("\n## ", 1)[0]
            else:  # PDFs: a blank line usually ends the statement
                raw = re.split(r"\n\s*\n(?!\s*(?:<|https?://))", body, 1)[0] if "\n\n" in body[40:] else body
            para = " ".join(raw.split())
            if len(para) < 15:
                continue
            # the span ends where the statement ends, so a following heading is still found
            seen_spans.append((m.start(g), start + len(raw)))
            if any(o.text == para for o in out):   # PLOS repeats the statement in front + back matter
                continue
            out.append(Statement(kind, " ".join(m.group(g).split()), para))
    return out


# ---------------------------------------------------------------- links

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'\]\)}\u200b]+(?:\([^\s)]*\))?[^\s<>\"'\]\)}.,;:]*", re.I)
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
    "10.7272": "nimh-data", "10.5285": "bodc-nerc-eds", "10.26093": "university-repo", "10.57745": "recherche-data-gouv",
}

HOSTS = {
    "github.com": ("github", "code"), "gitlab.com": ("gitlab", "code"),
    "bitbucket.org": ("bitbucket", "code"), "codeocean.com": ("codeocean", "code"),
    "softwareheritage.org": ("swh", "code"), "archive.softwareheritage.org": ("swh", "code"),
    "sourceforge.net": ("sourceforge", "code"), "code.google.com": ("googlecode", "code"),
    "github.io": ("github-pages", "web"), "gitlab.io": ("gitlab-pages", "web"),   # project sites "pypi.org": ("pypi", "code"),
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
    (re.compile(r"\bGSE\s*[:#]?\s*\d{4,8}\b"), "GEO"),
    (re.compile(r"\b(?:PRJNA|PRJEB|PRJDB|PRJCA)\d{3,8}\b"), "BioProject"),
    (re.compile(r"\b(?:CRA|GWH[A-Z]{4})\d{6,8}\b"), "GSA/NGDC"),
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
    own_web: bool = False              # body web resource introduced as "X is available at <url>"
    pre: str = ""                      # ~160 chars of text before the link (ownership / 'v1.2 (url)' cues)


DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2212\u00ad"), "-")


BOILERPLATE = re.compile(r"(?:^|\.)(?:creativecommons\.org|orcid\.org|crossmark\.crossref\.org|"
                         r"loop\.frontiersin\.org|copyright\.com|w3\.org|schema\.org)$")
# literature, not data: PubMed/PMC "Free Full Text" links of the reference list, F1000 referee reports
LITERATURE = re.compile(r"ncbi\.nlm\.nih\.gov/(?:pubmed|pmc)\b|pubmed\.ncbi\.nlm\.nih\.gov|"
                        r"europepmc\.org/(?:abstract|article)|doi\.org/10\.21956/", re.I)


def _clean_url(u: str) -> str:
    u = u.translate(DASHES).replace("\u200b", "")   # typeset hyphens / zero-width spaces
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


OWN_CUE = re.compile(
    r"(?:available|accessible|deposited|released|provided|found|obtained|downloaded|hosted|shared|archived)"
    r"\s+(?:\w+\s+){0,4}?(?:at|from|on|in|via|under)\b"
    r"|\bour\s+(?:\w+\s+)?(?:code|software|implementation|repository|scripts?|package|tool|pipeline|analysis)"
    r"|source\s+code|\bcode\s+(?:is|are|for|used|to)\b|scripts?\s+(?:is|are|used|to)\b"
    r"|\bwe\s+(?:provide|release|share|make)\b|implementation\s+(?:is|of\s+(?:our|the\s+proposed))",
    re.I)


THIRD_PARTY_SOURCE = re.compile(r"\b(?:downloaded|obtained|retrieved|taken|extracted|accessed)\b"
                                r"|\[\s*\d+(?:\s*[,\u2013-]\s*\d+)*\s*\]", re.I)


def sentence_before(pre: str) -> str:
    """Only the sentence the link sits in: '...can be found in Table 1. It is possible to use X (url'."""
    return re.split(r"(?<=[.!?])\s+(?=[A-Z(])", pre)[-1]


def _context(text: str, i: int, j: int, w: int = 120) -> str:
    return " ".join(text[max(0, i - w): j + w].split())


def _fix_pdf_breaks(text: str) -> str:
    """Re-join URLs broken across PDF line wraps (e.g. 'github.com/user/\\nrepo')."""
    text = re.sub(r"\b(github\.com|gitlab\.com|zenodo\.org|doi\.org|osf\.io) /", r"\1/", text)
    # '.' is deliberately not a join point: "github.com/x/repo.\n40th Conference" is a sentence end,
    # except for DOI stems that cannot end there: "10.5281/zenodo.\n906991"
    text = re.sub(r"(\b10\.\d{4,9}/(?:zenodo|m9\.figshare|dryad)\.)\s*\n\s*(?=\d|[a-z0-9]{5})", r"\1", text)
    text = re.sub(r"((?:https?://|github\.com/|zenodo\.org/|doi\.org/)\S*[/\-_=])\n(?=[\w\-])", r"\1", text)
    # word hyphenation outside URLs: "made publicly avail-\nable" -> "available"
    return re.sub(r"(?<![/\w.])([A-Za-z]{2,})-\n([a-z]{2,})\b", r"\1\2", text)


def _link_key(url: str) -> str:
    return re.sub(r"^https?://(?:www\.)?(?:dx\.)?(?:doi\.org/)?", "", url).lower().rstrip("/")


def _unglue_ref_number(url: str, text: str, hrefs: frozenset = frozenset()) -> str:
    """A reference number printed straight after a link gets glued onto it:
    '10.5281/zenodo.17789144110 <https://doi.org/10.5281/zenodo.17789144>' (ref 110),
    '.../DVN/ZJOUWB37.' (ref 37), 'github.com/rwnull/insitu_probe_generator64' (ref 64).
    Strip 1-3 trailing digits only when the shorter link appears on its own elsewhere in the
    paper (hyperlink target, link annotation or reference list) and the longer one is never a
    hyperlink target itself, so a real DOI ending in digits is left alone."""
    if not url[-1:].isdigit() or _link_key(url) in hrefs:
        return url
    for k in (1, 2, 3):
        short = url[:-k]
        if not short[-1].isalnum() or not url[-k].isdigit():
            break
        key = _link_key(short)
        if len(key) < 12:
            break
        if key in hrefs or re.search(re.escape(key) + r"(?![\w\-/])", text, re.I):
            return short
    return url


def find_links(body: str, statements: List[Statement], extra: Optional[List[str]] = None,
               self_doi: Optional[str] = None, full: Optional[str] = None) -> List[Link]:
    """Links worth auditing: everything in statements, plus repository-type links in the body."""
    found: dict = {}
    # hyperlink targets: PDF/JATS link annotations and '<url>' targets kept inline in JATS text
    hrefs = frozenset(_link_key(u) for u in list(extra or []) +
                      re.findall(r"<(https?://[^>\s]+)>", (full or body) + "\n" + "\n".join(s.text for s in statements)))

    def add(url: str, in_stmt, ctx: str, pre: str = ""):
        url = _unglue_ref_number(_clean_url(url), full or body, hrefs)
        if len(url) < 12:
            return
        host, kind, rt = classify_url(url)
        key = url.lower().rstrip("/")
        if self_doi and self_doi.lower() in key:
            return
        if key.endswith((".pdf",)) and kind == "other":
            return
        if BOILERPLATE.search(host) or LITERATURE.search(url):   # article licence, author IDs, cited papers
            return
        if key in found:
            if in_stmt and not found[key].in_statement:
                found[key].in_statement, found[key].stmt_kind = True, in_stmt
                found[key].pre = pre
            return
        found[key] = Link(url=url, host=host, kind=kind, repo_type=rt, in_statement=bool(in_stmt),
                          context=ctx, stmt_kind=in_stmt or None, pre=pre)

    web: set = set()
    srcs = [(s.text, s.kind) for s in statements] + [(_fix_pdf_breaks(body), None)]
    for src, in_stmt in srcs:
        hits = []
        for m in URL_RE.finditer(src):
            host, kind, _ = classify_url(_clean_url(m.group(0)))
            if in_stmt or kind != "other" and kind != "doi":
                hits.append((m.start(), m.end(), m.group(0)))
            elif kind == "other" and OWN_CUE.search(sentence_before(src[max(0, m.start() - 160):m.start()])):
                sent = sentence_before(src[max(0, m.start() - 160):m.start()])
                if not THIRD_PARTY_SOURCE.search(sent):   # "genes downloaded from the EcoGene site (url)"
                    web.add(_clean_url(m.group(0)).lower().rstrip("/"))   # "server is freely available at <url>"
                hits.append((m.start(), m.end(), m.group(0)))    # still checked: the paper relies on it
        for m in BARE_HOST_RE.finditer(src):
            hits.append((m.start(), m.end(), "https://" + m.group(1)))
        for m in DOI_TXT_RE.finditer(src):
            doi = _clean_url(m.group(1))
            if in_stmt or doi.split("/")[0] in REPO_DOI_PREFIX:
                hits.append((m.start(), m.end(), "https://doi.org/" + doi))
        for i, j, u in sorted(hits):   # keep reading order
            add(u, in_stmt, _context(src, i, j), " ".join(src[max(0, i - 160):i].split()))
    for key in web:
        if key in found and not found[key].in_statement:
            found[key].kind, found[key].own_web = "web", True
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
            acc = re.sub(r"\s*[:#]\s*|\s+", "", m.group(0))   # "GSE: 123209" -> "GSE123209"
            if acc not in seen:
                seen.add(acc)
                out.append({"id": acc, "db": db})
    return out


# ---------------------------------------------------------------- flags

ON_REQUEST = re.compile(
    r"(?:available|provided|obtained|shared|accessible|supplied|made\s+available)\s+"
    r"(?:\w+\s+){0,6}?(?:up)?on\s+(?:\w+\s+){0,2}request"
    r"|(?:up)?on\s+(?:reasonable\s+)?request\s+(?:from|to)\s+the\s+(?:corresponding\s+)?authors?"
    r"|(?:contact|request(?:ed)?\s+from)\s+the\s+corresponding\s+author"
    # Frontiers restricted-data template: "Requests to access these datasets should be directed to <name>"
    r"|requests\s+to\s+access\s+(?:these|the|this)\s+data(?:sets?)?\s+should\s+be\s+directed\s+to",
    re.I)
FUTURE = re.compile(r"will\s+(?:shortly\s+|soon\s+)?be\s+(?:made\s+)?(?:publicly\s+)?(?:available|released|deposited|shared)"
                    r"|(?:up)?on\s+(?:acceptance|publication)|coming\s+soon", re.I)
IN_PAPER = re.compile(
    # Frontiers boilerplate: "The original contributions presented in the study are included in the article/Supplementary material"
    # IOP: "All data that support the findings of this study are included within the article"
    r"(?:(?:all\s+)?(?:relevant\s+)?data(?:\s+that\s+supports?\s+the\s+findings\s+of\s+this\s+study)?|"
    r"original\s+contributions(?:\s+presented\s+in\s+the\s+study)?)\s+"
    r"(?:are|is|were)\s+(?:included|available|provided|contained|presented)\s+"
    r"(?:\w+\s+){0,3}(?:in|within)\s+the\s+(?:paper|article|manuscript|main\s+text|supplement\w*|supporting)",
    re.I)
NO_DATA = re.compile(r"no\s+(?:new\s+)?data\s+(?:were|was)\s+(?:generated|created|used)|"
                     r"(?:used|uses|generated|contains)\s+no\s+(?:new\s+)?data\b|"
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


MATERIALS = re.compile(r"\b(?:mice|mouse\s+lines?|plasmids?|strains?|cell\s+lines?|antibod\w+|reagents?|"
                       r"materials?|constructs?|animals|seeds?|samples?|specimens?|resources?|vectors?)\b", re.I)
DATA_OR_CODE = re.compile(r"\b(?:data(?:sets?)?|code|scripts?|software|analys[ie]s|results|models?)\b", re.I)


def is_materials_request(snippet: str) -> bool:
    """'Mice and plasmids ... are available upon request' concerns materials, not data/code."""
    sentence = re.split(r"(?<=[.;])\s+", snippet[:snippet.lower().rfind("request") + 7])[-1]
    return bool(MATERIALS.search(sentence)) and not DATA_OR_CODE.search(sentence)


def data_code_requests(text: str) -> List[str]:
    out = []
    for m in ON_REQUEST.finditer(text):
        snip = text[max(0, m.start() - 200):m.end()]
        if not is_materials_request(snip):
            out.append(_context(text, m.start(), m.end(), 80))
    return out


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


def _cited_only(url: str, refs: str, body: str) -> bool:
    """A PDF link annotation whose target is printed only in the reference list is a citation."""
    key = re.sub(r"^https?://(?:dx\.)?(?:doi\.org/)?", "", url).lower().rstrip("/")
    return len(key) > 8 and key in refs.lower() and key not in body.lower()


def extract(body: str, full: str, extra_links=None, self_doi=None) -> Extraction:
    full = full or body
    if extra_links and full.startswith(body):   # PDFs: body = full text minus the reference list
        refs = full[len(body):]
        extra_links = [u for u in extra_links if not _cited_only(u, refs, body)]
    full = _fix_pdf_breaks(full)   # statements need re-joined URLs too ("github.com/x/\nrepo")
    stmts = find_statements(full)
    stmt_text = "\n".join(s.text for s in stmts)
    scope = stmt_text + "\n" + body
    gen = sorted({m.group(0).lower() for m in GENERATED_DATA.finditer(body)})
    return Extraction(
        statements=stmts,
        links=find_links(body, stmts, extra_links, self_doi, full),
        accessions=find_accessions(scope),
        on_request=data_code_requests(scope)[:5],
        future_release=find_phrases(FUTURE, stmt_text),
        data_in_paper=find_phrases(IN_PAPER, stmt_text),
        no_data=find_phrases(NO_DATA, stmt_text),
        computational_hits=len(COMPUTATIONAL.findall(body)),
        generated_data_terms=gen,
        generated_data_verbs=find_phrases(GEN_VERBS, body, 3),
    )
