"""Messy-input robustness: nothing here may raise an uncaught exception."""
import json
import os
import sys

import pytest

from paper_audit import http, sources
from paper_audit.audit import audit
from paper_audit.cli import main
from paper_audit.extract import extract
from paper_audit.repocheck import scan_dir
from paper_audit.sources import jats_to_text, load_paper, pdf_to_text


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Any network call in these tests fails fast and deterministically."""
    monkeypatch.setenv("PAPER_AUDIT_REPLAY", str(tmp_path / "empty-replay"))
    monkeypatch.delenv("PAPER_AUDIT_CACHE", raising=False)


def run_cli(args, capsys):
    code = main(args)
    out = capsys.readouterr()
    return code, out.out, out.err


# ------------------------------------------------------------- CLI inputs

@pytest.mark.parametrize("bad", ["", "   ", "hello world", "10.", "arXiv:", "https://example.org/page"])
def test_unrecognised_input_is_clean_error(bad, capsys, tmp_path):
    code, out, err = run_cli([bad, "-o", str(tmp_path / "o"), "--no-clone"], capsys)
    assert code == 2
    assert "Traceback" not in err and "error:" in err


@pytest.mark.parametrize("content", [b"", b"%PDF-1.4\n garbage", b"\x00\xff\xfe" * 1000,
                                     "not a pdf at all ünïcode".encode("utf-16")])
def test_corrupt_pdf_does_not_crash(content, tmp_path, capsys):
    f = tmp_path / "bad.pdf"
    f.write_bytes(content)
    code, out, err = run_cli([str(f), "-o", str(tmp_path / "o"), "--no-clone", "-q"], capsys)
    assert code == 0
    r = json.loads((tmp_path / "o" / "bad.json").read_text())
    assert r["checklist"][0]["status"] == "FAIL"
    assert r["paper"]["warnings"]


def test_unicode_path(tmp_path, capsys):
    d = tmp_path / "Ünïcødé dir ✓"
    d.mkdir()
    f = d / "papér 論文.pdf"
    f.write_bytes(b"%PDF-1.4 broken")
    code, _, err = run_cli([str(f), "-o", str(d / "out"), "--no-clone", "-q"], capsys)
    assert code == 0 and "Traceback" not in err


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX non-root")
def test_unreadable_pdf(tmp_path, capsys):
    f = tmp_path / "locked.pdf"
    f.write_bytes(b"%PDF-1.4")
    f.chmod(0)
    try:
        code, _, err = run_cli([str(f), "-o", str(tmp_path / "o"), "--no-clone"], capsys)
    finally:
        f.chmod(0o600)
    assert code == 2 and "permission" in err.lower()


def test_directory_as_input(tmp_path, capsys):
    d = tmp_path / "folder.pdf"
    d.mkdir()
    code, _, err = run_cli([str(d), "-o", str(tmp_path / "o"), "--no-clone"], capsys)
    assert code == 2 and "Traceback" not in err


def test_symlink_loop_input(tmp_path, capsys):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.symlink_to(b)
    b.symlink_to(a)
    code, _, err = run_cli([str(a), "-o", str(tmp_path / "o"), "--no-clone"], capsys)
    assert code == 2 and "Traceback" not in err


def test_huge_garbage_pdf(tmp_path, capsys):
    f = tmp_path / "huge.pdf"
    with open(f, "wb") as fh:
        fh.write(b"%PDF-1.7\n")
        fh.write(os.urandom(1024) * 30_000)      # ~30 MB of noise
    code, _, err = run_cli([str(f), "-o", str(tmp_path / "o"), "--no-clone", "-q"], capsys)
    assert code == 0


def test_network_down_gives_clean_report(tmp_path, capsys):
    # DOI with no recorded responses: replay raises OfflineError -> must become a clean error
    code, _, err = run_cli(["10.1234/does-not-exist", "-o", str(tmp_path / "o"), "--no-clone"], capsys)
    assert code == 2 and "Traceback" not in err


# ------------------------------------------------------------- batch CSV

@pytest.mark.parametrize("raw", [
    b"",                                            # empty file
    b"doi\n",                                       # header only
    b"\xef\xbb\xbfdoi\n10.1/x\n",                   # UTF-8 BOM
    b"doi\n\n\n,\n#comment\n",                      # blanks / comments
    b"\xff\xfe\x00d\x00o\x00i\x00",                 # UTF-16 / non-UTF8
    b"\x89PNG\r\n\x1a\n\x00\x00binary",             # binary junk
])
def test_batch_messy_csv(raw, tmp_path, capsys):
    f = tmp_path / "in.csv"
    f.write_bytes(raw)
    code, _, err = run_cli(["--batch", str(f), "-o", str(tmp_path / "o"), "--no-clone", "-q"], capsys)
    assert code in (0, 2) and "Traceback" not in err
    if code == 0:
        assert (tmp_path / "o" / "summary.csv").exists()


def test_batch_missing_file(tmp_path, capsys):
    code, _, err = run_cli(["--batch", str(tmp_path / "nope.csv"), "-o", str(tmp_path / "o")], capsys)
    assert code == 2 and "Traceback" not in err


def test_batch_bom_header_is_read(tmp_path, capsys):
    from paper_audit.cli import _read_inputs
    f = tmp_path / "in.csv"
    f.write_bytes(b"\xef\xbb\xbfdoi,field\n10.1/abc,bio\n")
    assert _read_inputs(str(f)) == ["10.1/abc"]


# ------------------------------------------------------------- parsers

@pytest.mark.parametrize("xml", ["", "<article>", "<<<>>>", "\x00\x01", "<a><b></a>",
                                 "<article>" + "<sec>" * 5000 + "deep" + "</sec>" * 5000 + "</article>"])
def test_malformed_or_deep_xml(xml):
    try:
        body, full, links = jats_to_text(xml)
    except Exception as e:  # only a parse error is acceptable, never RecursionError etc.
        assert type(e).__name__ == "ParseError", type(e)
    else:
        assert isinstance(body, str)


def test_pdf_to_text_garbage():
    with pytest.raises(Exception):
        pdf_to_text(b"definitely not a pdf")
    assert sources.safe_pdf_to_text(b"definitely not a pdf")[0] == ""


@pytest.mark.parametrize("text", ["", "\x00" * 100, "Data availability" * 1000,
                                  "https://" * 500, "Code availability:\n" + "x" * 200000,
                                  "10.5281/zenodo." + "9" * 5000])
def test_extract_weird_text(text):
    ex = extract(text, text)
    assert isinstance(ex.links, list)


def test_crossref_weird_dates(monkeypatch):
    payload = {"message": {"title": None, "published": {"date-parts": [[None]]}, "link": None}}
    monkeypatch.setattr(http, "get_json", lambda *a, **k: payload)
    m = sources.crossref_meta("10.1234/x")
    assert m["published"] == ""


def test_load_paper_bad_xml_falls_back(monkeypatch):
    """Europe PMC returns junk XML and no PDF exists: warnings, no crash."""
    monkeypatch.setattr(sources, "crossref_meta", lambda d: {"title": "T"})
    monkeypatch.setattr(sources, "openalex", lambda d: {"ids": {"pmcid": "PMC1"}})
    monkeypatch.setattr(http, "request",
                        lambda url, **k: http.Resp(url, 200, b"<article><unclosed>", "text/xml"))
    p = load_paper("10.1234/x")
    assert p.text_source == "none" and p.warnings


# ------------------------------------------------------------- repo scan

def test_scan_dir_messy(tmp_path):
    (tmp_path / "loop").symlink_to(tmp_path)                 # symlink loop
    (tmp_path / "README.md").write_bytes(b"\xff\xfe\x00 binary readme \x80\x81")
    (tmp_path / "ünï 文件.py").write_text("print(1)")
    (tmp_path / "broken-link").symlink_to(tmp_path / "missing")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        res = scan_dir(tmp_path)
    finally:
        locked.chmod(0o700)
    assert {c["id"] for c in res["checks"]} >= {"readme", "dependency_file"}


def test_scan_dir_empty(tmp_path):
    res = scan_dir(tmp_path)
    assert not any(c["passed"] for c in res["checks"])


def test_audit_with_injected_empty_paper():
    p = sources.Paper(input="x", kind="pdf")
    r = audit("x", clone=False, paper=p)
    assert r["checklist"][0]["status"] == "FAIL"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_unwritable_output_dir(tmp_path, capsys):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        code, _, err = run_cli(["x.pdf", "-o", str(ro / "sub")], capsys)
    finally:
        ro.chmod(0o700)
    assert code == 2 and "cannot create output directory" in err
