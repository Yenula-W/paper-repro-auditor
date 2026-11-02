from paper_audit.extract import classify_url, extract, find_accessions, find_statements
from paper_audit.sources import classify_input, jats_to_text, strip_references

PDF_LIKE = """Introduction
We trained a neural network in Python using PyTorch. Simulations were run with custom code.
We performed RNA-seq on 12 samples.

Data availability
The datasets generated during the current study are available from the corresponding author on reasonable request.

Code availability
Source code is available at https://github.com/example-lab/
cool-model and archived at https://doi.org/10.5281/zenodo.1234567.

Acknowledgements
We thank everyone.

References
1. Smith J. Some tool. https://github.com/other/tool (2019).
"""


def test_statements_found_and_bounded():
    st = find_statements(PDF_LIKE)
    kinds = {s.kind for s in st}
    assert kinds == {"data", "code"}
    code = next(s for s in st if s.kind == "code")
    assert "We thank" not in code.text


def test_links_flags_and_wrapped_url():
    body = strip_references(PDF_LIKE)
    ex = extract(body, PDF_LIKE)
    urls = {l.url for l in ex.links}
    assert "https://github.com/example-lab/cool-model" in urls
    assert "https://doi.org/10.5281/zenodo.1234567" in urls
    assert not any("other/tool" in u for u in urls)   # reference list ignored
    assert ex.on_request
    assert "rna-seq" in ex.generated_data_terms
    assert ex.computational_hits >= 3


def test_classify_url():
    assert classify_url("https://github.com/a/b")[1:] == ("code", "github")
    assert classify_url("https://doi.org/10.5061/dryad.abc")[1:] == ("data", "dryad")
    assert classify_url("https://doi.org/10.5281/zenodo.1")[2] == "zenodo"
    assert classify_url("https://doi.org/10.1038/x")[1] == "doi"


def test_accessions():
    ids = {a["id"] for a in find_accessions("deposited in GEO (GSE123456) and PRIDE PXD012345.")}
    assert ids == {"GSE123456", "PXD012345"}


def test_classify_input():
    assert classify_input("10.1038/s41586-021-03819-2") == ("doi", "10.1038/s41586-021-03819-2")
    assert classify_input("https://doi.org/10.1371/journal.pone.0224321")[0] == "doi"
    assert classify_input("arXiv:1706.03762") == ("arxiv", "1706.03762")
    assert classify_input("https://arxiv.org/abs/1512.03385v1") == ("arxiv", "1512.03385")
    assert classify_input("10.48550/arXiv.1706.03762") == ("arxiv", "1706.03762")


def test_jats_keeps_hrefs_and_drops_refs():
    xml = """<article xmlns:xlink="http://www.w3.org/1999/xlink"><body>
    <sec><title>Methods</title><p>Code at <ext-link xlink:href="https://github.com/a/b">our repo</ext-link>.</p></sec>
    </body><back><sec sec-type="data-availability"><title>Data availability</title>
    <p>Data are in Dryad <ext-link xlink:href="https://doi.org/10.5061/dryad.x1">here</ext-link>.</p></sec>
    <ref-list><ref><ext-link xlink:href="https://github.com/cited/tool">t</ext-link></ref></ref-list></back></article>"""
    body, full, links = jats_to_text(xml)
    assert "https://github.com/a/b" in body
    assert "cited/tool" not in body and "cited/tool" in full
    ex = extract(body, full)
    assert any(s.kind == "data" and "dryad" in s.text for s in ex.statements)
    assert {l.repo_type for l in ex.links} >= {"github", "dryad"}
