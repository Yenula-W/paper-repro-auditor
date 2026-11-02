"""End-to-end audits replayed from recorded HTTP responses (no network)."""
import csv
import json
from pathlib import Path

import pytest

from paper_audit import http
from paper_audit.audit import audit
from paper_audit.cli import main
from paper_audit.report import to_markdown

FX = Path(__file__).parent / "fixtures"


@pytest.fixture
def replay(monkeypatch):
    def use(name):
        monkeypatch.setenv("PAPER_AUDIT_REPLAY", str(FX / name))
        monkeypatch.delenv("PAPER_AUDIT_CACHE", raising=False)
        monkeypatch.delenv("PAPER_AUDIT_RECORD", raising=False)
    return use


def status(r):
    return {i["id"]: i["status"] for i in r["checklist"]}


def test_on_request_paper(replay):
    # Sci Rep 2020: data AND Python scripts only "from the corresponding author on reasonable request"
    replay("10_1038_s41598-020-77660-4")
    r = audit("10.1038/s41598-020-77660-4", clone=False)
    s = status(r)
    assert r["paper"]["text_source"].startswith("europepmc:")
    assert s["data_statement"] == "PASS" and s["code_statement"] == "PASS"
    assert s["not_on_request"] == "FAIL"
    assert s["code_link"] == "FAIL"            # CRAN 'maps' is a cited tool, not the paper's code
    assert s["data_deposited"] == "FAIL"
    assert any(l.get("third_party") for l in r["evidence"]["links"])


def test_zenodo_paper(replay):
    # Nat Commun 2022: code + raw data on Zenodo
    replay("10_1038_s41467-022-33265-1")
    r = audit("10.1038/s41467-022-33265-1", clone=False)
    s = status(r)
    for k in ("data_statement", "code_statement", "code_link", "links_alive",
              "code_archived", "code_license", "version_pinned", "data_deposited"):
        assert s[k] == "PASS", k
    assert r["summary"]["score"] == 100
    md = to_markdown(r)
    assert "zenodo.7018108" in md and "## Checklist" in md


def test_arxiv_pdf(replay):
    # Attention Is All You Need: arXiv PDF, code link only in body text
    replay("arXiv_1706_03762")
    r = audit("arXiv:1706.03762", clone=False)
    s = status(r)
    assert r["paper"]["text_source"].startswith("pdf:")
    assert s["data_statement"] == "FAIL"
    assert s["code_statement"] == "WARN"
    assert s["code_link"] == "PASS"
    urls = [l["url"] for l in r["evidence"]["links"]]
    assert "https://github.com/tensorflow/tensor2tensor" in urls


def test_batch_cli(replay, tmp_path, monkeypatch, capsys):
    replay("10_1038_s41467-022-33265-1")
    inp = tmp_path / "dois.csv"
    inp.write_text("doi,note\n10.1038/s41467-022-33265-1,x\nnot-a-doi,bad\n")
    out = tmp_path / "out"
    assert main(["--batch", str(inp), "-o", str(out), "--no-clone", "-q"]) == 0
    rows = list(csv.DictReader(open(out / "summary.csv")))
    assert rows[0]["score"] == "100"
    assert rows[1]["error"]                      # bad input reported, batch continues
    assert json.loads((out / "10.1038_s41467-022-33265-1.json").read_text())["paper"]["doi"]
    assert (out / "summary.md").exists()


def test_replay_is_offline(replay):
    replay("10_1038_s41467-022-33265-1")
    with pytest.raises(http.OfflineError):
        http.request("https://example.org/never-recorded")
