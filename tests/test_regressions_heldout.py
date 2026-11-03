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


def test_version_cue_before_parenthesised_url():
    links = [_link("http://pyrx.sourceforge.net/", pre="the PyRx [64] virtual screening software (v0.8) from (")]
    mark_third_party(links)
    assert links[0].get("third_party") and not links[0].get("unclaimed")


# --- PLoS CB 1002284: "Software is available under the New BSD open source license ... at code.google.com"
def test_license_stated_in_paper_counts():
    paper = {"text_source": "x", "warnings": []}
    ex = {"statements": [{"kind": "code", "heading": "Software",
                          "text": "Software is available under the New BSD open source license and is freely "
                                  "available at http://code.google.com/p/gmv ."}],
          "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    links = [_link("http://code.google.com/p/gmv", pre="freely available at", in_statement=True, stmt_kind="code")]
    items = build_checklist(paper, ex, links, [])
    lic = next(i for i in items if i.id == "code_license")
    assert lic.status == "PASS" and "BSD" in lic.detail


# --- PeerJ 10.7717/peerj.6678: "R scripts to reproduce ... are available as a Supplemental File"
def test_code_in_data_statement_supplement():
    paper = {"text_source": "x", "warnings": []}
    ex = {"statements": [{"kind": "data", "heading": "Data availability",
                          "text": "R scripts to reproduce the examples, virtual experiments, and figures are "
                                  "available as a Supplemental File."}],
          "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 0, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    s = _status(build_checklist(paper, ex, [], []))
    assert s["code_statement"] == "PASS" and s["code_link"] == "WARN"


# --- Mol Biol Evol 10.1093/molbev/msab231: China NGDC accessions
def test_ngdc_accessions():
    ids = {a["id"] for a in find_accessions("deposited with accession codes PRJCA004227 and CRA003432")}
    assert ids == {"PRJCA004227", "CRA003432"}


# --- Sci Adv 10.1126/sciadv.abi8605 and BMC Bioinf 10.1186/1471-2105-13-216: journal-specific headings
def test_science_and_bmc_headings():
    t = ("## Data and materials availability:\nAll code and data are publicly available at "
         "https://doi.org/10.5281/zenodo.5206676 .\n\n## Availability and requirements\nProject home page: "
         "https://sourceforge.net/projects/gennonh/ License: GNU GPL\n\n## References\n")
    kinds = {st.heading.lower(): st.kind for st in find_statements(t)}
    assert kinds == {"data and materials availability": "both", "availability and requirements": "code"}


# --- Lancet Glob Health 10.1016/s2214-109x(21)00392-2 is a review article; NumPy (dev set) too
def test_review_article_not_penalised():
    paper = {"text_source": "x", "warnings": [], "article_type": "review-article"}
    ex = {"statements": [], "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    s = _status(build_checklist(paper, ex, [], []))
    assert s["data_statement"] == s["code_statement"] == s["data_deposited"] == "N/A"


def test_lancet_data_sharing_heading():
    st = find_statements("## Data sharing\nDe-identified participant data will be shared on request.\n\n## References\n")
    assert st and st[0].kind == "data"


# --- arXiv 2610.05265: the only code repo 404s; the license message must not blame the host type
def test_license_message_when_repo_dead():
    paper = {"text_source": "x", "warnings": []}
    ex = {"statements": [], "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    links = [_link("https://github.com/x/review-repo", pre="Our code is available at", alive=False, status=404)]
    lic = next(i for i in build_checklist(paper, ex, links, []) if i.id == "code_license")
    assert lic.status == "WARN" and "not reachable" in lic.detail


# --- Sci Adv 10.1126/sciadv.abi8605: run-in head inside the acknowledgements paragraph
def test_run_in_heading():
    t = ("Competing interests: none. Data and materials availability: All code and data are available at "
         "https://doi.org/10.5281/zenodo.5206676 .\n")
    st = find_statements(t)
    assert st and st[0].kind == "both" and "zenodo" in st[0].text
    assert not find_statements("We discuss data availability in general terms here.\n")


# --- Mol Biol Evol: "accession codes PRJCA004227" is not a code statement
def test_accession_codes_are_not_code():
    from paper_audit.audit import CODE_MENTION
    assert not CODE_MENTION.search("deposited with the accession codes PRJCA004227")
    assert CODE_MENTION.search("All data and scripts are available")


def test_bmc_software_product_review_is_research():
    paper = {"text_source": "x", "warnings": [], "article_type": "product-review"}
    ex = {"statements": [], "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    assert _status(build_checklist(paper, ex, [], []))["data_statement"] == "FAIL"


# --- arXiv 1709.04065 (FLaapLUC): PDF quirks hid the authors' own repo and broke a Zenodo DOI
def test_pdf_quirks_flaapluc():
    from paper_audit.sources import Paper
    raw = ("FLaapLUC (Lenain, 2017) has been made publicly avail-\nable on GitHub at github.com /jlenain/flaapluc, "
           "and contributions are welcome.\nLenain, J.-P., 2017. Astrophysics Source Code Library. doi: 10.5281/zenodo.\n906991, ascl.")
    fixed = _fix_pdf_breaks(raw)
    assert "publicly available on GitHub at github.com/jlenain/flaapluc" in fixed
    assert "10.5281/zenodo.906991" in fixed
    urls = {l.url for l in find_links(raw, [])}
    assert {"https://github.com/jlenain/flaapluc", "https://doi.org/10.5281/zenodo.906991"} <= urls
    links = [_link("https://github.com/jlenain/flaapluc", pre="see also the code at the address in footnote 3")]
    mark_third_party(links, "FLaapLUC: a pipeline for the generation of prompt alerts on transient Fermi-LAT gamma-ray sources")
    assert not links[0].get("third_party")
    assert "https://github.com/a/repo-\nname" not in _fix_pdf_breaks("x")   # URL hyphens untouched below
    assert _fix_pdf_breaks("https://github.com/jjackson-\neco/repo") == "https://github.com/jjackson-eco/repo"


# --- arXiv 2609.12862 (simulation physics): "we measured" alone is not evidence of undeposited data
def test_verbs_alone_do_not_fail_data():
    paper = {"text_source": "x", "warnings": []}
    ex = {"statements": [], "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 10, "accessions": [], "generated_data_terms": ["we measured"],
          "generated_data_verbs": ["we measured"]}
    assert _status(build_checklist(paper, ex, [], []))["data_deposited"] == "WARN"


# --- PLOS (README quickstart paper 10.1371/journal.pone.0224321): statement repeated in meta + back
def test_duplicate_statements_collapsed():
    t = "## Data Availability\nAll data are on OSF https://osf.io/x .\n\n## Data Availability Statement\nAll data are on OSF https://osf.io/x .\n"
    assert len(find_statements(t)) == 1


# ===================== ship-bar round 1 (10 new journals) =====================

# --- Phys Rev Research 10.1103/physrevresearch.2.023290, A&A 10.1051/0004-6361/201937108:
#     OpenAlex now lists OA copies under "locations" (not "oa_locations"), so the arXiv PDF was never tried
def test_openalex_locations_are_tried(monkeypatch):
    from paper_audit import sources
    tried = []
    monkeypatch.setattr(sources, "crossref_meta", lambda d: {"title": "T"})
    monkeypatch.setattr(sources, "europepmc_pmcid", lambda d: None)
    monkeypatch.setattr(sources, "openalex", lambda d: {
        "open_access": {"is_oa": True},
        "best_oa_location": {"pdf_url": "https://publisher.example/blocked.pdf"},
        "locations": [{"is_oa": True, "pdf_url": "https://arxiv.org/pdf/2002.05448"},
                      {"is_oa": False, "pdf_url": "https://closed.example/x.pdf"}]})
    monkeypatch.setattr(sources, "_fetch_pdf", lambda u: tried.append(u))
    p = sources.load_paper("10.1103/physrevresearch.2.023290")
    assert "https://arxiv.org/pdf/2002.05448" in tried and "https://closed.example/x.pdf" not in tried
    assert p.is_oa is True


# --- Glossa 10.5334/gjgl.583, MDPI Economies 10.3390/economies12070176: open access, but the
#     publisher blocks automated downloads -> not a FAIL of the paper
def test_open_access_but_blocked_is_warn():
    base = {"text_source": "none", "warnings": ["no open-access full text retrievable"]}
    assert _status(build_checklist({**base, "is_oa": True}, {}, [], []))["full_text"] == "WARN"
    assert _status(build_checklist({**base, "is_oa": False}, {}, [], []))["full_text"] == "FAIL"


# --- Wellcome Open Res 10.12688/wellcomeopenres.16323.1 (PDF): reference number 37 glued onto
#     the Dataverse DOI ("…/DVN/ZJOUWB37.") -> reported as a dead link
def test_reference_number_glued_to_doi():
    body = "Harvard Dataverse: Replication Data. https://doi.org/10.7910/DVN/ZJOUWB37. The project"
    full = body + "\nReferences\n37. Ngari MM: Replication Data. http://www.doi.org/10.7910/DVN/ZJOUWB\n"
    urls = {l.url for l in find_links(body, [], full=full)}
    assert urls == {"https://doi.org/10.7910/DVN/ZJOUWB"}
    # a DOI that really ends in digits is left alone
    z = "Code: https://doi.org/10.5281/zenodo.1234567. See also zenodo.12345 elsewhere."
    assert {l.url for l in find_links(z, [], full=z)} == {"https://doi.org/10.5281/zenodo.1234567"}


# --- same paper: F1000/Wellcome "Extended data <repository>:" is part of the statement, while a
#     Nature "Extended Data" heading still ends it
def test_f1000_extended_data_kept_in_statement():
    t = ("\nData availability\nUnderlying data Harvard Dataverse: Replication data. https://doi.org/10.7910/DVN/X.\n"
         "Extended data Harvard Dataverse: Replication data. This project contains analysis_v1.do (STATA script).\n"
         "\nAcknowledgments\nThanks.")
    st = find_statements(t)
    assert "STATA script" in st[0].text and "Thanks" not in st[0].text
    n = "\nData availability\nAll data are in the Source Data files provided with this paper.\nExtended data\nFig. 1 shows"
    assert "Fig. 1" not in find_statements(n)[0].text


# --- same paper: STATA .do scripts deposited in the Dataverse record are the paper's archived code
def test_scripts_in_data_archive_count_as_code():
    text = ("Underlying data Harvard Dataverse: https://doi.org/10.7910/DVN/ZJOUWB. Extended data: "
            "post-discharge analysis.do (STATA script that runs the analysis). Data are available under CC BY 4.0.")
    st = [{"kind": "data", "heading": "Data availability", "text": text}]
    ex = {"statements": st, "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 8, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    l = _link("https://doi.org/10.7910/DVN/ZJOUWB", in_statement=True, stmt_kind="data", archived_doi=True)
    s = _status(build_checklist({"text_source": "pdf", "warnings": []}, ex, [l], []))
    assert s["code_link"] == s["code_archived"] == s["code_license"] == s["data_deposited"] == "PASS"
    # "Discharge_diagnosis codes.csv" alone is a data file, not code
    from paper_audit.audit import CODE_MENTION
    assert not CODE_MENTION.search("Discharge_diagnosis codes.csv (list of codes for discharge diagnosis)."[:30])


# --- same paper: PubMed / PMC "Free Full Text" links in the reference list are not data deposits
def test_pubmed_links_are_literature():
    urls = {l.url for l in find_links("text", [], extra=["http://www.ncbi.nlm.nih.gov/pubmed/26254555",
                                                         "http://www.ncbi.nlm.nih.gov/pmc/articles/6091952",
                                                         "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE1"])}
    assert urls == {"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE1"}


# --- PeerJ CS 10.7717/peerj-cs.735: "The article used no data as it is a literature review."
def test_literature_review_statement_needs_no_code_or_data():
    t = "\nData Availability\nThe following information was supplied regarding data availability: The article used no data as it is a literature review.\n"
    ex = extract("We trained deep learning models, neural network, machine learning, convolutional.", t)
    from dataclasses import asdict
    s = _status(build_checklist({"text_source": "x", "warnings": []}, asdict(ex), [], []))
    assert s["code_statement"] == s["code_link"] == s["data_deposited"] == "N/A"


# --- Front Vet Sci 10.3389/fvets.2024.1415423: Frontiers boilerplate puts the data in the
#     article/supplement -> WARN, not "no data deposited" FAIL
def test_frontiers_original_contributions_in_article():
    t = ("\nData availability statement\nThe original contributions presented in the study are included in the "
         "article/Supplementary material, further inquiries can be directed to the corresponding author.\n")
    ex = extract("We sampled 1,170 cattle and tested the serum. A questionnaire was administered.", t)
    assert ex.data_in_paper
    from dataclasses import asdict
    s = _status(build_checklist({"text_source": "x", "warnings": []}, asdict(ex), [], []))
    assert s["data_deposited"] == "WARN" and s["not_on_request"] == "PASS"


# --- GMD 10.5194/gmd-15-3281-2022: "The NACC code is available at <Zenodo>" in a combined
#     code-and-data section does not make the Zenodo software record a data deposit
def test_code_archive_is_data_only_if_its_sentence_says_data():
    text = ("The NACC code is publicly available at https://doi.org/10.5281/zenodo.5507489 and via GitHub. "
            "The GFS data are available in GRIB2 format at https://www.nco.ncep.noaa.gov/pmb/products/gfs/ (NOAA).")
    st = [{"kind": "both", "heading": "Code and data availability", "text": text}]
    ex = {"statements": st, "on_request": [], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 30, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    z = _link("https://doi.org/10.5281/zenodo.5507489", in_statement=True, stmt_kind="both", archived_doi=True, kind="code")
    w = _link("https://www.nco.ncep.noaa.gov/pmb/products/gfs/", in_statement=True, stmt_kind="both")
    assert _status(build_checklist({"text_source": "x", "warnings": []}, ex, [z, w], []))["data_deposited"] == "WARN"


# ===================== ship-bar round 2 (10 more new journals) =====================

# --- New J Phys 10.1088/1367-2630/acca9c: PDF text lost the spaces ("Dataavailabilitystatement")
def test_heading_without_spaces():
    t = "systems.\nDataavailabilitystatement\nAll data that support the findings of this study are included within the article.\n"
    st = find_statements(t)
    assert st and st[0].kind == "data"
    assert extract("body", t).data_in_paper


# --- HESS 10.5194/hess-24-2999-2020: URL broken at the PDF line end inside the statement
#     ("github.com/sapfluxnet/\nsapfluxnet-public/wiki"), the GitHub wiki holds a database (data,
#     not code), and "Model source code is available upon request" is about code only
def test_hess_data_on_github_and_code_on_request():
    full = ("\nCode and data availability. Sapflux data are archived in\nthe sapfluxnet database "
            "(https://github.com/sapfluxnet/\nsapfluxnet-public/wiki; Poyatos, 2017). Model source code "
            "is available upon request from Kersti Haahti.\n\nSupplement.")
    ex = extract("We ran a numerical model simulation of the water balance (Python).", full)
    urls = {l.url for l in ex.links}
    assert "https://github.com/sapfluxnet/sapfluxnet-public/wiki" in urls
    from dataclasses import asdict
    links = [_link(l.url, pre=l.pre, in_statement=l.in_statement, stmt_kind=l.stmt_kind) for l in ex.links]
    s = _status(build_checklist({"text_source": "pdf", "warnings": []}, asdict(ex), links, []))
    assert s["code_link"] == "FAIL" and s["not_on_request"] == "FAIL"
    assert s["code_archived"] == "N/A" and "code_license" not in s
    assert s["data_deposited"] == "WARN"   # data only on a git host (round 3: no DOI archive -> WARN)


# --- JOSS 10.21105/joss.02673: PDF link annotations of the reference list (a figshare DOI of a
#     cited paper) were counted as data deposits
def test_pdf_annotation_only_in_references_is_ignored():
    body = "DrWatson is a Julia package. See the docs."
    full = body + "\nReferences\nAmstutz P. (2016). Common Workflow Language. doi: 10.6084/m9.figshare.3115156.v2\n"
    ex = extract(body, full, extra_links=["https://doi.org/10.6084/m9.figshare.3115156.v2",
                                          "https://zenodo.org/record/4133570"])
    assert {l.url for l in ex.links} == {"https://zenodo.org/record/4133570"}


# --- same paper: "DrWatson: the perfect sidekick ..." owns github.com/JuliaDynamics/DrWatson.jl
def test_julia_suffix_repo_named_in_title():
    from paper_audit.audit import _named_in_title
    assert _named_in_title({"url": "https://github.com/JuliaDynamics/DrWatson.jl"},
                           "DrWatson: the perfect sidekick for your scientific inquiries")


# ===================== ship-bar round 3 (10 more new journals) =====================

# --- ESSD 10.5194/essd-14-3997-2022: numbered Copernicus heading "6 Code and data availability",
#     a BODC dataset DOI (10.5285) and "will shortly be made available"
def test_essd_numbered_heading_bodc_and_future():
    full = ("\n6 Code and data availability\nThe data are made available via the British Oceanographic\n"
            "Data Centre (BODC), via https://doi.org/10.5285/e6974644-\n2026-0f94-e053-6c86abc00109 (Loveday, 2022).\n"
            "Access to the code for the primary productivity processor will\nshortly be made available via "
            "https://github.com/timjsmyth/\nGliderPP (Loveday and Smyth, 2020).\n7 Conclusions\nThis paper")
    ex = extract("We processed glider data with a Python processor.", full)
    assert ex.statements and ex.statements[0].kind == "both"
    assert ex.future_release
    urls = {l.url for l in ex.links}
    assert "https://doi.org/10.5285/e6974644-2026-0f94-e053-6c86abc00109" in urls
    assert "https://github.com/timjsmyth/GliderPP" in urls
    assert classify_url("https://doi.org/10.5285/e6974644-2026-0f94-e053-6c86abc00109")[2] == "bodc-nerc-eds"


# --- Front Neuroinform 10.3389/fninf.2020.613666: Frontiers restricted-data template
def test_frontiers_requests_to_access_is_on_request():
    t = ("\nData Availability Statement\nThe data analyzed in this study is subject to the following licenses/"
         "restrictions: The authors do not have permission to share data. Requests to access these datasets "
         "should be directed to Qiyang Lu, x@example.org.\n")
    assert extract("body", t).on_request


# --- npj Comput Mater 10.1038/s41524-022-00889-2: "Samples of our datasets are available at
#     <github>", full data on request -> data only on a git host (WARN), not "deposited"
def test_data_sample_on_github_is_not_a_deposit():
    text = ("Samples of our datasets are available at https://github.com/m/topo/tree/main/data_sample. "
            "The full training datasets are available from the corresponding author upon reasonable request.")
    st = [{"kind": "data", "heading": "DATA AVAILABILITY", "text": text},
          {"kind": "code", "heading": "CODE AVAILABILITY", "text": "Source code is available at https://github.com/m/topo."}]
    ex = {"statements": st, "on_request": [text[90:]], "future_release": [], "data_in_paper": [], "no_data": [],
          "computational_hits": 60, "generated_data_terms": [], "generated_data_verbs": [], "accessions": []}
    d = _link("https://github.com/m/topo/tree/main/data_sample", in_statement=True, stmt_kind="data",
              pre="Samples of our datasets are available at")
    c = _link("https://github.com/m/topo", in_statement=True, stmt_kind="code", pre="Source code is available at")
    items = build_checklist({"text_source": "pdf", "warnings": []}, ex, [d, c], [])
    s = _status(items)
    assert s["data_deposited"] == "WARN" and s["code_link"] == "PASS"
    assert "on request" in [i for i in items if i.id == "data_deposited"][0].detail


# --- data_deposited and not_future missed the bar on untouched rounds: off unless --experimental
def test_experimental_checks_are_opt_in():
    from paper_audit.audit import audit
    from paper_audit.sources import Paper
    p = Paper(input="x", kind="pdf", text_source="pdf:x",
              text="We sequenced RNA-seq. Data will be made available upon publication.",
              full_text="\nData availability\nData will be made available upon publication.\n")
    off = {i["id"] for i in audit("x", clone=False, paper=p)["checklist"]}
    on = {i["id"] for i in audit("x", clone=False, paper=p, experimental=True)["checklist"]}
    assert "data_deposited" not in off and "not_future" not in off
    assert {"data_deposited", "not_future"} <= on


# ===================== candidate screening (Nov-Dec 2025 papers) =====================

# --- Commun Biol 10.1038/s42003-025-09382-0 (JATS) and 10.1038/s42003-025-09398-6: a superscript
#     reference number printed after a DOI that ends in a digit ("zenodo.17789144" + ref 110) was
#     glued on and reported as a dead link, while the hyperlink target holds the real DOI
def test_reference_number_glued_to_digit_doi():
    stmt = ("Custom-written analysis scripts are shared at https://github.com/Canelab-USAL/Mismatch or "
            "10.5281/zenodo.17789144110 <https://doi.org/10.5281/zenodo.17789144>.")
    st = [Statement("code", "Code availability", stmt)]
    urls = {l.url for l in find_links("body", st, full="\n## Code availability\n" + stmt)}
    assert "https://doi.org/10.5281/zenodo.17789144" in urls
    assert not any("17789144110" in u for u in urls)
    # upper-case target, three glued digits (ref 154), and a ref number glued onto a GitHub repo name
    stmt2 = ("The exact version of the code has been archived on Zenodo under the 10.5281/zenodo.17705168154 "
             "<https://doi.org/10.5281/ZENODO.17705168>.")
    body = "designed using insitu_probe_generator.py (https://github.com/rwnull/insitu_probe_generator64) and"
    urls = {l.url.lower() for l in find_links(body, [Statement("code", "Code availability", stmt2)], full=stmt2 + body,
                                              extra=["https://github.com/rwnull/insitu_probe_generator"])}
    assert "https://doi.org/10.5281/zenodo.17705168" in urls
    assert "https://github.com/rwnull/insitu_probe_generator" in urls
    assert not any(u.endswith(("154", "generator64")) for u in urls)
    # a real DOI that ends in digits and is itself the hyperlink target is never shortened
    real = "Data: 10.5281/zenodo.7047191 <https://doi.org/10.5281/zenodo.7047191>; see also 10.5281/zenodo.70471."
    assert "https://doi.org/10.5281/zenodo.7047191" in {l.url for l in find_links("b", [Statement("data", "Data availability", real)], full=real)}


# --- Phys Rev (APS) 10.1103/fnhb-bzqr via arXiv 2608.08544: letter-spaced small-caps heading
#     "DA T A A V AILABILITY" was missed, and "10.5281/zen-\nodo.17975543" became a dead "zen-" link
def test_aps_spaced_caps_heading_and_zenodo_hyphenation():
    from paper_audit.sources import collapse_spaced_caps
    raw = ("FIG. A.1. The scheme of optical detection in this experiment.\nDA T A A V AILABILITY\n"
           "The data that support the findings of this article are\nopenly available [65], embargo periods may apply.\n"
           "Appendix A: Optical detection method\n")
    st = find_statements(collapse_spaced_caps(raw))
    assert st and st[0].kind == "data" and "openly available" in st[0].text
    refs = ("[65] Y. Sheng, Data for: Levitated milligram-scale ferromag-\nnetic magnetometer at room temperature, "
            "10.5281/zen-\nodo.17975543 (2025).\n")
    ex = extract(raw + refs, raw + refs)
    urls = {l.url for l in ex.links}
    assert "https://doi.org/10.5281/zenodo.17975543" in urls
    assert not any(u.rstrip("/").endswith("zen-") for u in urls)


# --- npj Digit Med 10.1038/s41746-026-03406-7 (AnySleep, PDF): "https://doi.\norg/10.25822/nx52-bc11"
#     gave a dead "https://doi.org/10", and a Box share ID wrapped mid-token gave a truncated 404 URL
def test_anysleep_wrapped_host_and_share_id():
    st_text = ("All datasets analyzed during the current study are publicly available. In the\nfollowing, we list "
               "the datasets and the URLs to access them: ABC (https://doi.\norg/10.25822/nx52-bc11), CCSHS ( "
               "https://doi.org/10.25822/cg2n-4y91),\nCHAT ( https://doi.org/10.\n25822/d68d-8g03), SSC ( https://stanfordmedicine.app.box.com/s/r9e92ygq0erf7hn5re6j51\n"
               "aaggf50jly), CAP ( https://doi.org/10.13026/C2VC79).\n")
    full = "\nData availability\n" + st_text + "\nCode availability\nCode at https://github.com/dslaborg/AnySleep.\n"
    urls = {l.url for l in extract("We trained a deep learning model.", full).links}
    assert "https://doi.org/10.25822/nx52-bc11" in urls
    assert "https://stanfordmedicine.app.box.com/s/r9e92ygq0erf7hn5re6j51aaggf50jly" in urls
    assert "https://doi.org/10.25822/d68d-8g03" in urls
    assert "https://doi.org/10" not in urls and not any(u.endswith("6j51") for u in urls)
    # a hyphen inside a DOI suffix wrapped at the line end is kept: "10.25822/xmwv-\nyz91"
    assert "https://doi.org/10.25822/xmwv-yz91" in {l.url for l in extract(
        "b", "\nData availability\nWSC ( https://doi.org/10.25822/xmwv-\nyz91), MESA.\n").links}


# --- bioRxiv 10.64898/2026.01.22.700881: manuscript line numbers ran into statements
#     ("upon 652 \nreasonable request.  653")
def test_biorxiv_line_numbers_stripped():
    from paper_audit.sources import strip_line_numbers
    lines = [f"Methods sentence number {i} about kettle lakes and amphibians. {600 + i} " for i in range(50)]
    lines += ["Data availability statement: Data are available from the corresponding author upon 652 ",
              "reasonable request.  653 ", "Conflict of interest statement: The authors declare none. 654 "]
    out = strip_line_numbers("\n".join(lines))
    assert "upon\nreasonable request." in out and " 652" not in out and " 653" not in out
    assert "number 7 about" in out                       # numbers inside sentences are untouched
    # ordinary text whose lines happen to end in a number is left alone
    plain = "\n".join(f"Table row {i}: value {i * 37 % 101}" for i in range(40))
    assert strip_line_numbers(plain) == plain
