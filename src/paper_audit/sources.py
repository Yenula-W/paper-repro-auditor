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


def classify_input(s: str) -> tuple[str, str]:
    s = s.strip()
    if s.lower().endswith(".pdf") and (Path(s).exists() or s.startswith("http")):
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
    if Path(s).exists():
        return "pdf", s
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
    root = ET.fromstring(xml)
    links: List[str] = []

    def walk(el, out, skip_refs):
        tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
        if skip_refs and tag in ("ref-list", "ref"):
            return
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
        if tag in ("p", "sec", "notes", "fn", "statement"):
            out.append("\n\n")
        if el.tail:
            out.append(el.tail)

    body_parts: List[str] = []
    full_parts: List[str] = []
    walk(root, full_parts, skip_refs=False)
    links_full = list(links)
    links.clear()
    walk(root, body_parts, skip_refs=True)
    norm = lambda s: re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", s))  # noqa: E731
    return norm("".join(body_parts)), norm("".join(full_parts)), list(dict.fromkeys(links_full))


# ---------------------------------------------------------------- metadata

def crossref_meta(doi: str) -> dict:
    j = http.get_json(f"https://api.crossref.org/works/{quote(doi)}")
    if not j:
        return {}
    m = j.get("message", {})
    parts = (m.get("published") or m.get("published-online") or m.get("issued") or {}).get("date-parts") or [[]]
    date = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parts[0])) if parts[0] else ""
    return {
        "title": (m.get("title") or [""])[0],
        "journal": (m.get("container-title") or [""])[0],
        "published": date,
        "links": [l.get("URL") for l in m.get("link", []) if l.get("URL")],
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


def _use_pdf(p: Paper, data: bytes, source: str) -> None:
    text, links = pdf_to_text(data)
    p.full_text = text
    p.text = strip_references(text)
    p.pdf_links = links
    p.text_source = source


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
            data = Path(ident).read_bytes()
        _use_pdf(p, data, f"pdf:{ident}")
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
        if data:
            _use_pdf(p, data, f"pdf:{url}")
            return p
    p.warnings.append("no open-access full text retrievable (tried Europe PMC, OpenAlex/Unpaywall PDFs)")
    return p
