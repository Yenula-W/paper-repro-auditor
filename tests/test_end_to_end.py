"""End-to-end audits on synthetic HTTP responses (no network, no third-party content).

See tests/synthetic.py for the invented papers and API payloads.
"""
import csv
import json

import pytest

from paper_audit import http
from paper_audit.audit import audit
from paper_audit.cli import main
from paper_audit.report import to_markdown

import synthetic as syn


@pytest.fixture
def net(monkeypatch):
    for v in ("PAPER_AUDIT_REPLAY", "PAPER_AUDIT_CACHE", "PAPER_AUDIT_RECORD"):
        monkeypatch.delenv(v, raising=False)
    missing = syn.install(monkeypatch)
    yield missing


def status(r):
    return {i["id"]: i["status"] for i in r["checklist"]}


def test_on_request_paper(net):
    # data AND Python scripts only "from the corresponding author on reasonable request"
    r = audit(syn.ON_REQUEST_DOI, clone=False, experimental=True)
    s = status(r)
    assert r["paper"]["text_source"].startswith("europepmc:")
    assert s["data_statement"] == "PASS" and s["code_statement"] == "PASS"
    assert s["not_on_request"] == "FAIL"
    assert s["code_link"] == "FAIL"            # CRAN 'maps' is a cited tool, not the paper's code
    assert s["data_deposited"] == "FAIL"
    assert any(l.get("third_party") for l in r["evidence"]["links"])


def test_zenodo_paper(net):
    # code + raw data on Zenodo
    r = audit(syn.ZENODO_DOI, clone=False, experimental=True)
    s = status(r)
    for k in ("data_statement", "code_statement", "code_link", "links_alive",
              "code_archived", "code_license", "version_pinned", "data_deposited"):
        assert s[k] == "PASS", k
    assert r["summary"]["score"] == 100
    md = to_markdown(r)
    assert "zenodo.7018108" in md and "## Checklist" in md
    assert not net


def test_experimental_off_by_default(net):
    s = status(audit(syn.ZENODO_DOI, clone=False))
    assert "data_deposited" not in s and s["code_link"] == "PASS"


def test_arxiv_pdf(net):
    # arXiv PDF, code link only in body text
    r = audit(f"arXiv:{syn.ARXIV_ID}", clone=False)
    s = status(r)
    assert r["paper"]["text_source"].startswith("pdf:")
    assert s["data_statement"] == "FAIL"
    assert s["code_statement"] == "WARN"
    assert s["code_link"] == "PASS"
    urls = [l["url"] for l in r["evidence"]["links"]]
    assert "https://github.com/example-lab/seqmodel" in urls


def test_batch_cli(net, tmp_path):
    inp = tmp_path / "dois.csv"
    inp.write_text(f"doi,note\n{syn.ZENODO_DOI},x\nnot-a-doi,bad\n")
    out = tmp_path / "out"
    assert main(["--batch", str(inp), "-o", str(out), "--no-clone", "-q"]) == 0
    rows = list(csv.DictReader(open(out / "summary.csv")))
    assert rows[0]["score"] == "100"
    assert rows[1]["error"]                      # bad input reported, batch continues
    assert json.loads((out / "10.5555_example.zenodo.json").read_text())["paper"]["doi"]
    assert (out / "summary.md").exists()


def test_record_then_replay_offline(tmp_path, monkeypatch):
    """Record mode saves responses; replay serves them and refuses anything unrecorded."""
    store = tmp_path / "rec"
    real = http.Resp("https://example.org/x", 200, b'{"a": 1}', "application/json")
    k = http._key("GET", "https://example.org/x", None)
    http._save(store, k, "https://example.org/x", real)
    monkeypatch.setenv("PAPER_AUDIT_REPLAY", str(store))
    monkeypatch.delenv("PAPER_AUDIT_CACHE", raising=False)
    assert http.get_json("https://example.org/x") == {"a": 1}
    with pytest.raises(http.OfflineError):
        http.request("https://example.org/never-recorded")
