"""Turn an input (DOI, arXiv id, PDF path/URL) into metadata + full text.

Open APIs only: Crossref, OpenAlex, Europe PMC, arXiv, optional Unpaywall.
"""
from __future__ import annotations

import io
import logging
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from . import http

logging.getLogger("pypdf").setLevel(logging.ERROR)

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
ARXIV_NEW = re.compile(r"(?:arxiv[:/ ]\s*|arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(v\d+)?", re.I)
ARXIV_OLD = re.compile(r"(?:arxiv[:/ ]\s*|arxiv\.org/(?:abs|pdf)/)([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.I)
XLINK = "{http://www.w3.org/1999/xlink}href"
BLOCK_TAGS = {"td", "th", "tr", "list-item", "label", "caption", "table-wrap", "fig", "break",
              "disp-quote", "def-item", "term", "def", "mixed-citation", "element-citation"}


@dataclass
class Paper:
    input: str
    kind: str = ""                 # doi | arxiv | pdf
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    title: str = ""
    journal: str = ""
    published: str = ""            # YYYY-MM-DD (best effort)
    text: str = ""                 # body text, references stripped where possible
    full_text: str = ""            # everything incl. back matter (for statements)
    text_source: str = "none"
    pdf_links: List[str] = field(default_factory=list)   # link annotations from PDF
    warnings: List[str] = field(default_factory=list)


def _is_file(s: str) -> bool:
    try:
        return Path(s).is_file()
    except (OSError, ValueError):   # symlink loops, NUL bytes, over-long names
        return False


def classify_input(s: str) -> tuple:
    s = (s or "").strip()
    if not s:
        raise ValueError("empty input: give a DOI, arXiv id or PDF path")
    if s.lower().startswith("http") and s.lower().split("?")[0].endswith(".pdf"):
        return "pdf", s
    if _is_file(s):
        return "pdf", s
    m = re.search(r"10\.48550/arxiv\.(.+)$", s, re.I)
    if m:
        return "arxiv", m.group(1)
    if "arxiv" in s.lower() or re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", s):
        for rx in (ARXIV_NEW, ARXIV_OLD):
            m = rx.search(s)
            if m:
                return "arxiv", m.group(1)
    m = DOI_RE.search(s)
    if m:
        return "doi", m.group(1).rstrip(".,;)").lower()
    try:
        exists = Path(s).exists() or Path(s).is_symlink()
    except (OSError, ValueError):
        exists = True
    if exists:
        raise ValueError(f"not a readable PDF file: {s!r}")
    raise ValueError(f"cannot recognise input as DOI, arXiv id or PDF: {s!r}")


# ---------------------------------------------------------------- PDF

def pdf_to_text(data: bytes) -> tuple[str, List[str]]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages, links = [], []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:  # noqa: BLE001 - broken pages shouldn't kill the audit
            pages.append("")
        try:
            for a in p.get("/Annots") or []:
                a = a.get_object()
                uri = (a.get("/A") or {}).get("/URI")
                if uri:
                    links.append(str(uri))
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(pages), list(dict.fromkeys(links))


def safe_pdf_to_text(data: bytes) -> tuple:
    """pdf_to_text that never raises: returns ('', [], error_message) on unparsable input."""
    try:
        text, links = pdf_to_text(data)
        return text, links, ""
    except Exception as e:  # noqa: BLE001 - pypdf raises many types on corrupt files
        return "", [], f"PDF could not be parsed ({type(e).__name__})"


REF_HEAD = re.compile(r"^\s*(references|bibliography|references and notes|literature cited)\s*$",
                      re.I | re.M)


def strip_references(text: str) -> str:
    """Drop the reference list (last 'References' heading onward, if in the back half)."""
    ms = list(REF_HEAD.finditer(text))
    if ms and ms[-1].start() > len(text) * 0.4:
        return text[: ms[-1].start()]
    return text


# ---------------------------------------------------------------- JATS XML

def jats_to_text(xml: str) -> tuple[str, str, List[str]]:
    """Return (body_text_without_refs, full_text, links) from JATS XML."""
    from .extract import classify_url   # local import: extract does not import sources
    root = ET.fromstring(xml)
    links: List[str] = []

    # numbered citations ("archived in Zenodo [50]") -> the cited repository URL/DOI
    ref_urls = {}
    for ref in root.iter():
        if not (isinstance(ref.tag, str) and ref.tag.split("}")[-1] == "ref" and ref.get("id")):
            continue
        urls = [e.get(XLINK) for e in ref.iter() if e.get(XLINK)]
        urls = ["https://doi.org/" + u if u.startswith("10.") else u for u in urls]
        urls += ["https://doi.org/" + d.rstrip(".,;)") for d in DOI_RE.findall(" ".join(ref.itertext()))]
        urls += ["https://doi.org/" + (e.text or "").strip() for e in ref.iter()
                 if isinstance(e.tag, str) and e.tag.endswith("pub-id") and e.get("pub-id-type") == "doi" and e.text]
        keep = [u for u in urls if classify_url(u)[1] not in ("other", "doi")]
        if keep:
            ref_urls[ref.get("id")] = list(dict.fromkeys(keep))

    def walk(el, out, skip_refs):
        tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
        if skip_refs and tag in ("ref-list", "ref"):
            return
        if tag == "ref-list":           # hard section boundary even when the list has no <title>
            out.append("\n\n## References\n")
        if tag == "custom-meta":
            name = el.findtext("meta-name") or ""
            val_el = el.find("meta-value")
            out.append(f"\n\n## {name.strip()}\n")
            if val_el is not None:
                walk(val_el, out, skip_refs)
            out.append("\n\n")
            return
        if tag == "title":
            out.append("\n\n## " + "".join(el.itertext()).strip() + "\n")
            if el.tail:
                out.append(el.tail)
            return
        if el.text:
            out.append(el.text)
        for c in el:
            walk(c, out, skip_refs)
        if tag in ("ext-link", "uri", "self-uri"):
            href = el.get(XLINK) or ""
            if href:
                links.append(href)
                if href not in "".join(el.itertext()):
                    out.append(f" <{href}>")
        if tag == "xref" and el.get("ref-type") == "bibr":
            for rid in (el.get("rid") or "").split():
                for u in ref_urls.get(rid, []):
                    out.append(f" <{u}>")
        if tag in ("p", "sec", "notes", "fn", "statement"):
            out.append("\n\n")
        elif tag in BLOCK_TAGS:     # table cells, list items...: keep words/URLs apart
            out.append("\n")
        if el.tail:
            out.append(el.tail)

    body_parts: List[str] = []
    full_parts: List[str] = []
    try:
        walk(root, full_parts, skip_refs=False)
        links_full = list(links)
        links.clear()
        walk(root, body_parts, skip_refs=True)
    except RecursionError:   # pathologically nested XML: flat text, no section structure
        flat = " ".join(root.itertext())
        hrefs = [e.get(XLINK) for e in root.iter() if e.get(XLINK)]
        return flat, flat, list(dict.fromkeys(hrefs))
    norm = lambda s: re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", s))  # noqa: E731
    return norm("".join(body_parts)), norm("".join(full_parts)), list(dict.fromkeys(links_full))


# ---------------------------------------------------------------- metadata

def crossref_meta(doi: str) -> dict:
    j = http.get_json(f"https://api.crossref.org/works/{quote(doi)}")
    if not j:
        return {}
    m = j.get("message", {})
    parts = (m.get("published") or m.get("published-online") or m.get("issued") or {}).get("date-parts") or [[]]
    nums = [x for x in (parts[0] or []) if isinstance(x, int)]
    date = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(nums))
    return {
        "title": (m.get("title") or [""])[0] or "",
        "journal": (m.get("container-title") or [""])[0] or "",
        "published": date,
        "links": [l.get("URL") for l in (m.get("link") or []) if isinstance(l, dict) and l.get("URL")],
    }


def openalex(doi: str) -> dict:
    return http.get_json(f"https://api.openalex.org/works/https://doi.org/{quote(doi)}") or {}


def europepmc_pmcid(doi: str) -> Optional[str]:
    j = http.get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&query="
                      + quote(f'DOI:"{doi}"'))
    for r in ((j or {}).get("resultList") or {}).get("result", []):
        if r.get("pmcid") and r.get("isOpenAccess") == "Y":
            return r["pmcid"]
    return None


def arxiv_meta(aid: str) -> dict:
    r = http.request(f"http://export.arxiv.org/api/query?id_list={aid}")
    if not r.ok:
        return {}
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    try:
        e = ET.fromstring(r.content).find("a:entry", ns)
    except ET.ParseError:
        return {}
    if e is None:
        return {}
    return {
        "title": " ".join((e.findtext("a:title", "", ns) or "").split()),
        "published": (e.findtext("a:published", "", ns) or "")[:10],
        "doi": e.findtext("x:doi", None, ns),
        "journal": e.findtext("x:journal_ref", "", ns) or "arXiv",
    }


def _fetch_pdf(url: str) -> Optional[bytes]:
    r = http.request(url, browser=True)
    if r.ok and r.content[:5] == b"%PDF-":
        return r.content
    return None


def _use_pdf(p: Paper, data: bytes, source: str) -> bool:
    text, links, err = safe_pdf_to_text(data)
    if err or not text.strip():
        p.warnings.append(err or "PDF contains no extractable text (scanned image?)")
        return False
    p.full_text = text
    p.text = strip_references(text)
    p.pdf_links = links
    p.text_source = source
    return True


def load_paper(inp: str) -> Paper:
    kind, ident = classify_input(inp)
    p = Paper(input=inp, kind=kind)

    if kind == "pdf":
        if ident.startswith("http"):
            data = _fetch_pdf(ident)
            if not data:
                p.warnings.append("could not download PDF")
                return p
        else:
            try:
                data = Path(ident).read_bytes()
            except PermissionError:
                raise ValueError(f"permission denied reading {ident!r}") from None
            except OSError as e:
                raise ValueError(f"cannot read {ident!r}: {e.strerror or e}") from None
        if not _use_pdf(p, data, f"pdf:{ident}"):
            return p
        m = DOI_RE.search(p.full_text[:5000])
        if m:
            p.doi = m.group(1).rstrip(".,;)").lower()
            meta = crossref_meta(p.doi)
            p.title, p.journal, p.published = meta.get("title", ""), meta.get("journal", ""), meta.get("published", "")
        return p

    if kind == "arxiv":
        p.arxiv_id = ident
        meta = arxiv_meta(ident)
        p.title, p.published, p.journal = meta.get("title", ""), meta.get("published", ""), meta.get("journal", "arXiv")
        p.doi = (meta.get("doi") or "").lower() or None
        data = _fetch_pdf(f"https://arxiv.org/pdf/{ident}")
        if data:
            _use_pdf(p, data, f"pdf:https://arxiv.org/pdf/{ident}")
        else:
            p.warnings.append("arXiv PDF download failed")
        return p

    # DOI
    p.doi = ident
    meta = crossref_meta(ident)
    if not meta:
        p.warnings.append("DOI not found in Crossref")
    p.title, p.journal, p.published = meta.get("title", ""), meta.get("journal", ""), meta.get("published", "")
    oa = openalex(ident)
    if not p.title:
        p.title = oa.get("title") or ""
    if not p.published:
        p.published = oa.get("publication_date") or ""

    # 1) Europe PMC structured full text (best: keeps hyperlinks + section titles)
    pmcid = ((oa.get("ids") or {}).get("pmcid") or "").rstrip("/").rsplit("/", 1)[-1]
    if pmcid and not pmcid.upper().startswith("PMC"):
        pmcid = "PMC" + pmcid
    pmcid = pmcid or europepmc_pmcid(ident)
    if pmcid:
        r = http.request(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML")
        if r.ok and b"<article" in r.content[:5000]:
            try:
                p.text, p.full_text, p.pdf_links = jats_to_text(r.text)
                p.text_source = f"europepmc:{pmcid}"
                return p
            except ET.ParseError:
                p.warnings.append("Europe PMC XML unparsable")

    # 2) open-access PDF candidates (OpenAlex, Unpaywall, Crossref links)
    cands: List[str] = []
    for loc in [oa.get("best_oa_location") or {}] + (oa.get("oa_locations") or []):
        if loc.get("pdf_url"):
            cands.append(loc["pdf_url"])
    email = os.environ.get("UNPAYWALL_EMAIL")
    if email:
        u = http.get_json(f"https://api.unpaywall.org/v2/{quote(ident)}?email={quote(email)}") or {}
        for loc in u.get("oa_locations") or []:
            if loc.get("url_for_pdf"):
                cands.append(loc["url_for_pdf"])
    cands += [l for l in meta.get("links", []) if "pdf" in l.lower()]
    for url in dict.fromkeys(cands):
        data = _fetch_pdf(url)
        if data and _use_pdf(p, data, f"pdf:{url}"):
            return p
    p.warnings.append("no open-access full text retrievable (tried Europe PMC, OpenAlex/Unpaywall PDFs)")
    return p
