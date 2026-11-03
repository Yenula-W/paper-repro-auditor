"""Regression tests for wrong judgments found while hand-checking the 28-paper held-out set.

Each test names the paper whose real text exposed the bug (see EVALUATION.md).
"""
from paper_audit import http, resolve
from paper_audit.audit import build_checklist, mark_third_party
from paper_audit.extract import (Statement, _fix_pdf_breaks, classify_url, extract, find_accessions,
                                 find_links, find_statements)
from paper_audit.resolve import LinkResult, _alive
from paper_audit.sources import jats_to_text

NS = 'xmlns:xlink="http://www.w3.org/1999/xlink"'


def _link(url, pre="", in_statement=False, stmt_kind=None, **kw):
    host, kind, rt = classify_url(url)
    d = dict(url=url, repo_type=rt, kind=kind, in_statement=in_statement, stmt_kind=stmt_kind, pre=pre,
             status=200, alive=True, final_url=url, archived_doi=False, license=None, repo=None,
             clone_url=None, pinned_ref=None, releases_before_pub=[], commits_after_pub=None,
             linked_github=None, notes=[], stars=None)
    d.update(kw)
    return d


def _status(items):
    return {i.id: i.status for i in items}


# --- Cell Rep 10.1016/j.celrep.2019.09.064: key-resources table cells were glued together,
#     producing fake URLs like https://github.com/nservant/HiC-ProIGB (reported dead)
def test_table_cells_do_not_glue_urls():
    xml = f"""<article {NS}><body><table-wrap><table><tr>
      <td><ext-link xlink:href="https://github.com/nservant/HiC-Pro">https://github.com/nservant/HiC-Pro</ext-link></td>
      <td>IGB</td></tr></table></table-wrap></body></article>"""
    body, full, _ = jats_to_text(xml)
    urls = {l.url for l in find_links(body, [])}
    assert urls == {"https://github.com/nservant/HiC-Pro"}


# --- Genome Biol 10.1186/s13059-020-02153-6: "archived in Zenodo [50]" - the DOI lives in the
#     reference list, so the statement looked link-less
def test_numbered_citation_resolves_to_repository_doi():
    xml = f"""<article {NS}><body/><back>
      <sec><title>Availability of data and materials</title>
      <p>All program code is available via Zenodo <xref ref-type="bibr" rid="CR50">50</xref>
         and the paper we compare to <xref ref-type="bibr" rid="CR3">3</xref>.</p></sec>
      <ref-list><ref id="CR50"><mixed-citation>Code. Zenodo.
         <pub-id pub-id-type="doi">10.5281/zenodo.3835378</pub-id></mixed-citation></ref>
      <ref id="CR3"><mixed-citation>Other paper. <pub-id pub-id-type="doi">10.1038/nature1</pub-id>
      </mixed-citation></ref></ref-list></back></article>"""
    body, full, _ = jats_to_text(xml)
    ex = extract(body, full)
    urls = {l.url for l in ex.links}
    assert "https://doi.org/10.5281/zenodo.3835378" in urls
    assert not any("nature1" in u for u in urls)        # ordinary citations are not data links


# --- Ecol Evol 10.1002/ece3.9623: printed URL uses U+2010 hyphen ("jjackson‐eco")
def test_unicode_hyphen_in_url_is_normalised():
    st = [Statement("data", "Data availability", "Code at https://github.com/jjackson‐eco/repo .")]
    urls = {l.url for l in find_links("", st)}
    assert urls == {"https://github.com/jjackson-eco/repo"}


# --- Cell Rep: "Mice and plasmids ... available upon request" is about materials, not data
def test_materials_on_request_is_not_data_on_request():
    txt = ("## Lead contact and materials availability\nMice and plasmids generated in this study are "
           "available upon request via a material transfer agreement.\n\n## Data and code availability\n"
           "Data have been deposited in GEO with the accession GSE: 123209.\n")
    ex = extract(txt, txt)
    assert ex.on_request == []
    assert [a["id"] for a in ex.accessions] == ["GSE123209"]
    txt2 = "## Data availability\nThe data are available from the corresponding author upon reasonable request.\n"
    assert extract(txt2, txt2).on_request


def test_combined_heading_without_code_is_not_code_statement():
    paper = {"text_source": "x", "warnings": []}
    ex = {"statements": [{"kind": "both", "heading": "Data and code availability",
                          "text": "ATAC-seq data have been deposited in GEO under GSE123209."}],
          "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "generated_data_terms": [], "generated_data_verbs": [],
          "accessions": [{"id": "GSE123209", "db": "GEO"}]}
    s = _status(build_checklist(paper, ex, [], []))
    assert s["data_statement"] == "PASS"
    assert s["code_statement"] == "WARN"


# --- PLoS Comput Biol 10.1371/journal.pcbi.1002284: code on Google Code under a "Software" section
def test_google_code_and_software_section():
    assert classify_url("http://code.google.com/p/gmv")[2] == "googlecode"
    st = find_statements("## Software\nSoftware is freely available at http://code.google.com/p/gmv .\n\n## Results\n")
    assert st and st[0].kind == "code"


def test_google_code_uses_archive(monkeypatch):
    seen = []

    def fake(url, **k):
        seen.append(url)
        return http.Resp(url, 200, b"{}", "application/json")
    monkeypatch.setattr(http, "request", fake)
    res = LinkResult("http://code.google.com/p/gmv", "googlecode", "code", True)
    resolve.check_googlecode(res)
    assert res.alive is True and "google-code-archive" in seen[0]
    assert any("read-only archive" in n for n in res.notes)


# --- arXiv 2610.04953: footnote "available at https://github.com/ValleyC/EDISCO.\n40th Conference"
def test_pdf_line_join_does_not_eat_next_sentence():
    assert "EDISCO.40th" not in _fix_pdf_breaks("https://github.com/ValleyC/EDISCO.\n40th Conference")
    assert _fix_pdf_breaks("https://github.com/user/\nrepo") == "https://github.com/user/repo"


# --- PLoS One 10.1371/journal.pone.0156543, Cell Rep, PLoS CB 1002147: cited tools counted as own code
def test_cited_tools_are_not_own_code():
    links = [
        _link("https://github.com/HongjianLi/idock", pre="the program idock [33] (v2.1.3) was downloaded from ("),
        _link("http://pyrx.sourceforge.net/", pre="the PyRx [64] virtual screening software (v0.8) from ("),
        _link("https://github.com/taoliu/MACS/", pre="Software and algorithms MACS2 Zhang et al., 2008"),
        _link("https://github.com/kemerelab/ghostipy/issues/2", pre="see"),
        _link("https://github.com/lab/ourtool", pre="Our implementation is freely available at"),
        _link("https://github.com/lab/ourtool-data", pre="Figure scripts"),
    ]
    mark_third_party(links)
    tp = {l["url"]: bool(l.get("third_party")) for l in links}
    assert tp["https://github.com/HongjianLi/idock"]
    assert tp["http://pyrx.sourceforge.net/"]
    assert tp["https://github.com/taoliu/MACS/"]
    assert tp["https://github.com/kemerelab/ghostipy/issues/2"]
    assert not tp["https://github.com/lab/ourtool"]
    assert not tp["https://github.com/lab/ourtool-data"]      # same owner as an own link


def test_unclaimed_code_links_downgrade_to_warn():
    paper = {"text_source": "x", "warnings": []}
    ex = {"statements": [], "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    links = [_link("https://github.com/x/y", pre="1")]
    mark_third_party(links)
    assert _status(build_checklist(paper, ex, links, []))["code_link"] == "WARN"


# --- Google Code / any server returning 5xx is not proof the link is dead
def test_server_error_is_unknown_not_dead():
    assert _alive("u", http.Resp("u", 503, b"")) is None
    assert _alive("u", http.Resp("u", 404, b"")) is False


# --- R Soc Open Sci 10.1098/rsos.200664: "analyses codes ... can be found on https://osf.io/3nxpg/";
#     a personal github.io page was counted as code
def test_osf_with_codes_counts_as_code_and_github_io_does_not():
    from paper_audit.audit import _is_code
    osf = _link("https://osf.io/3nxpg/", pre="All experimental and analyses codes and materials can be found on",
                in_statement=True, stmt_kind="data")
    page = _link("https://fredvbrug.github.io/openScience.html", pre="see")
    assert _is_code(osf)
    assert page["kind"] == "web" and not _is_code(page)


# --- arXiv 2610.04953 (ML paper) got "methods mention crystal structure" - terms alone are not evidence
def test_generated_data_message_needs_verbs():
    paper = {"text_source": "x", "warnings": []}
    base = {"statements": [], "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
            "computational_hits": 0, "accessions": [], "generated_data_terms": ["crystal structure"]}
    items = build_checklist(paper, {**base, "generated_data_verbs": []}, [], [])
    d = next(i for i in items if i.id == "data_deposited")
    assert d.status == "WARN" and "crystal" not in d.detail
    items = build_checklist(paper, {**base, "generated_data_verbs": ["we collected"]}, [], [])
    assert next(i for i in items if i.id == "data_deposited").status == "FAIL"


def test_find_accessions_dedupes_spacing_variants():
    ids = [a["id"] for a in find_accessions("GSE: 123209 and GSE123209 and GSE #57500")]
    assert ids == ["GSE123209", "GSE57500"]


# --- Genome Biol: the reference holds the Zenodo DOI only as plain text / relative href
def test_citation_doi_in_plain_reference_text():
    xml = f"""<article {NS}><body/><back><sec><title>Data availability</title>
      <p>All program code is available via Zenodo <xref ref-type="bibr" rid="CR50">50</xref>.</p></sec>
      <ref-list><ref id="CR50"><mixed-citation>Benchmark container v2.0.1. Zenodo. 2019.
      10.5281/zenodo.2628061.</mixed-citation></ref></ref-list></back></article>"""
    body, full, _ = jats_to_text(xml)
    assert "https://doi.org/10.5281/zenodo.2628061" in {l.url for l in extract(body, full).links}


# --- eNeuro 10.1523/eneuro.0202-21.2021: ownership cue from the previous sentence leaked in
def test_ownership_cue_is_sentence_local():
    links = [_link("https://github.com/OverLordGoldDragon/ssqueezepy/",
                   pre="An overview can be found in Table 1. It is possible to use other packages (OverLordGold Dragon,")]
    mark_third_party(links)
    assert links[0].get("third_party")


def test_readme_inline_install_counts_as_run_step(tmp_path):
    from paper_audit.repocheck import scan_dir
    (tmp_path / "README.md").write_text("# tool\n## Installation\nThe easiest way is ```pip install ghostipy```.\n" + "x" * 300)
    c = {c["id"]: c["passed"] for c in scan_dir(tmp_path)["checks"]}
    assert c["readme_run_steps"]


# --- NAR 10.1093/nar/gku294: web-server paper; the server URL is only in running text
def test_web_server_link_is_checked_and_warns():
    body = "The CAD-score web server is freely available at http://www.ibt.lt/bioinformatics/cad-score ."
    links = find_links(body, [])
    assert [(l.kind, l.own_web, l.pre.endswith("available at")) for l in links] == [("web", True, True)]
    paper = {"text_source": "x", "warnings": []}
    ex = {"statements": [], "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    d = _link("http://www.ibt.lt/bioinformatics/cad-score", pre="freely available at", own_web=True)
    d["kind"] = "web"
    assert _status(build_checklist(paper, ex, [d], []))["code_link"] == "WARN"


# --- PLoS CB 10.1371/journal.pcbi.1002284: third-party data sites are checked but are not "own web service"
def test_third_party_data_site_is_not_own_web():
    body = "Genes were downloaded from the EcoGene web site [10] (http://ecogene.org) for testing."
    links = find_links(body, [])
    assert len(links) == 1 and links[0].own_web is False
