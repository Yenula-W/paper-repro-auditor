from paper_audit.repocheck import scan_dir


def _ids(res):
    return {c["id"]: c["passed"] for c in res["checks"]}


def test_good_repo(tmp_path):
    (tmp_path / "requirements.txt").write_text("numpy\n")
    (tmp_path / "LICENSE").write_text("MIT")
    (tmp_path / "run_analysis.py").write_text("print(1)")
    (tmp_path / "README.md").write_text("# Tool\n\n## Usage\n\n```\npip install -r requirements.txt\npython run_analysis.py\n```\n" + "x" * 300)
    c = _ids(scan_dir(tmp_path))
    assert c == {"dependency_file": True, "readme": True, "readme_run_steps": True,
                 "entry_point": True, "license_file": True}


def test_bare_repo(tmp_path):
    (tmp_path / "stuff.txt").write_text("hi")
    (tmp_path / "README").write_text("Run analysis/missing.R to get figures.")
    c = _ids(scan_dir(tmp_path))
    assert not c["dependency_file"] and not c["readme"] and not c["readme_run_steps"]
    assert not c["license_file"] and c["readme_scripts_exist"] is False
