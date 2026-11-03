"""Synthetic HTTP responses for the end-to-end tests.

Everything here is invented: example DOIs, titles, statements and API payloads that mimic the
shape of Crossref, OpenAlex, Europe PMC, arXiv, GitHub, Zenodo and CRAN responses. No third-party
paper text or metadata is stored in the repository.
"""
import json
import zlib
from urllib.parse import urlsplit

from paper_audit import http

ON_REQUEST_DOI = "10.5555/example.onrequest"
ZENODO_DOI = "10.5555/example.zenodo"
ARXIV_ID = "2501.00001"

JATS = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink" article-type="research-article">
<front><article-meta><title-group><article-title>{title}</article-title></title-group></article-meta></front>
<body>
<sec><title>Methods</title><p>{methods}</p></sec>
</body>
<back>
{back}
<ref-list><title>References</title><ref id="R1"><mixed-citation>Example A. A cited paper. 2019.</mixed-citation></ref></ref-list>
</back>
</article>"""


def _jats_on_request() -> str:
    return JATS.format(
        title="Synthetic network growth on a lattice",
        methods=("We ran numerical simulations of network growth written in Python and fitted a "
                 "regression model. Maps were drawn with the R package maps "
                 '(<ext-link xlink:href="https://cran.r-project.org/web/packages/maps/index.html">'
                 "https://cran.r-project.org/web/packages/maps/index.html</ext-link>), version 3.3."),
        back=("<sec><title>Data availability</title><p>The datasets and Python scripts used in this study "
              "are available from the corresponding author on reasonable request.</p></sec>"))


def _jats_zenodo() -> str:
    return JATS.format(
        title="A synthetic soil microbiome time series",
        methods=("We sequenced 16S rRNA amplicons (RNA-seq for a subset) and analysed them with custom "
                 "Python scripts and a machine learning pipeline."),
        back=('<sec><title>Data availability</title><p>Raw sequencing data are deposited in Zenodo '
              '(<ext-link xlink:href="https://doi.org/10.5281/zenodo.7047191">https://doi.org/10.5281/zenodo.7047191</ext-link>).</p></sec>'
              '<sec><title>Code availability</title><p>The analysis code is available at '
              '<ext-link xlink:href="https://doi.org/10.5281/zenodo.7018108">https://doi.org/10.5281/zenodo.7018108</ext-link>.</p></sec>'))


def _crossref(doi: str, title: str) -> dict:
    return {"message": {"DOI": doi, "title": [title], "container-title": ["Journal of Examples"],
                        "published": {"date-parts": [[2022, 9, 1]]}, "link": []}}


def _openalex(pmcid: str, title: str) -> dict:
    return {"title": title, "publication_date": "2022-09-01", "ids": {"pmcid": pmcid},
            "open_access": {"is_oa": True}, "best_oa_location": {}, "locations": []}


def _zenodo(rid: str, kind: str, lic: str, version: str) -> dict:
    return {"id": int(rid), "doi": f"10.5281/zenodo.{rid}",
            "metadata": {"title": f"Example {kind}", "resource_type": {"type": kind},
                         "license": {"id": lic}, "version": version, "related_identifiers": []}}


def pdf_with_lines(lines) -> bytes:
    """A minimal one-page PDF whose text layer holds `lines` (Helvetica, one line each)."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT", "/F1 9 Tf", "11 TL", "40 800 Td"] + [f"({esc(l)}) Tj T*" for l in lines] + ["ET"]
    stream = zlib.compress("\n".join(ops).encode("latin-1"))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


ARXIV_LINES = [
    "A Synthetic Sequence Model",
    "Abstract",
    "We train a neural network for sequence transduction on GPU hardware.",
    "1 Introduction",
    "Deep learning models trained with stochastic gradient descent dominate this task.",
    "We implemented the model in Python and trained it on a public benchmark.",
    "The code we used to train and evaluate our models is available at",
    "https://github.com/example-lab/seqmodel .",
    "2 Results",
    "Our model improves the score by two points.",
]

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
<entry><title>A Synthetic Sequence Model</title><published>2025-01-02T00:00:00Z</published></entry>
</feed>"""


def routes() -> dict:
    j = lambda o: (200, "application/json", json.dumps(o).encode())  # noqa: E731
    gh = "https://api.github.com/repos/example-lab/seqmodel"
    return {
        # on-request paper
        f"https://api.crossref.org/works/{ON_REQUEST_DOI}": j(_crossref(ON_REQUEST_DOI, "Synthetic network growth on a lattice")),
        f"https://api.openalex.org/works/https://doi.org/{ON_REQUEST_DOI}": j(_openalex("PMC1000001", "Synthetic network growth on a lattice")),
        "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC1000001/fullTextXML": (200, "application/xml", _jats_on_request().encode()),
        "https://cran.r-project.org/web/packages/maps/index.html": (200, "text/html", b"<html>maps</html>"),
        # Zenodo paper
        f"https://api.crossref.org/works/{ZENODO_DOI}": j(_crossref(ZENODO_DOI, "A synthetic soil microbiome time series")),
        f"https://api.openalex.org/works/https://doi.org/{ZENODO_DOI}": j(_openalex("PMC1000002", "A synthetic soil microbiome time series")),
        "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC1000002/fullTextXML": (200, "application/xml", _jats_zenodo().encode()),
        "https://zenodo.org/api/records/7047191": j(_zenodo("7047191", "dataset", "cc-by-4.0", "1.0")),
        "https://zenodo.org/api/records/7018108": j(_zenodo("7018108", "software", "mit", "v1.0.0")),
        # arXiv paper
        f"https://export.arxiv.org/api/query?id_list={ARXIV_ID}": (200, "application/atom+xml", ATOM.encode()),
        f"https://arxiv.org/pdf/{ARXIV_ID}": (200, "application/pdf", pdf_with_lines(ARXIV_LINES)),
        gh: j({"full_name": "example-lab/seqmodel", "html_url": "https://github.com/example-lab/seqmodel",
               "clone_url": "https://github.com/example-lab/seqmodel.git", "license": {"spdx_id": "Apache-2.0"},
               "stargazers_count": 12, "size": 300, "archived": False, "pushed_at": "2025-03-01T00:00:00Z"}),
        f"{gh}/releases?per_page=100": j([{"tag_name": "v1.0", "published_at": "2025-01-10T00:00:00Z"}]),
        f"{gh}/tags?per_page=100": j([{"name": "v1.0"}]),
    }


def _norm(url: str) -> str:
    u = urlsplit(url)
    return f"https://{u.netloc}{u.path}" + (f"?{u.query}" if u.query else "")


def install(monkeypatch) -> list:
    """Route http.request to the synthetic responses; returns the list of unknown URLs asked for."""
    table = {_norm(k): v for k, v in routes().items()}
    missing = []

    def fake(url, method="GET", headers=None, max_bytes=40_000_000, browser=False, retry=True):
        hit = table.get(_norm(url))
        if hit is None:
            if "api.github.com" in url and "/commits" in url:
                hit = (200, "application/json", b"[]")
            else:
                missing.append(url)
                return http.Resp(url, 404, b"", "text/plain")
        status, ctype, body = hit
        return http.Resp(url, status, body, ctype)

    monkeypatch.setattr(http, "request", fake)
    return missing
