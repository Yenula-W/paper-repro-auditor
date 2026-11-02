"""Light, self-contained checks on a linked code repository.

Kept deliberately small with a stable interface so it can later be swapped for the
`repro-debt-scanner` package:

    check_repo(clone_url, ref=None) -> dict   # clones, then calls scan_dir
    scan_dir(path)                  -> dict   # {"checks": [{"id","passed","detail"}], ...}
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

DEP_FILES = [
    "requirements.txt", "requirements.in", "environment.yml", "environment.yaml", "setup.py",
    "setup.cfg", "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "conda.yml",
    "renv.lock", "DESCRIPTION", "Project.toml", "Manifest.toml", "package.json", "Dockerfile",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "CMakeLists.txt", "install.R",
    "Singularity", "apptainer.def", "default.nix", "flake.nix", "uv.lock", "pixi.toml",
]
ENTRY_GLOBS = [
    "main.py", "run*.py", "run*.sh", "run*.R", "Makefile", "Snakefile", "workflow/Snakefile",
    "*.nf", "main.R", "main.m", "*.Rmd", "*.qmd", "*.ipynb", "train*.py", "reproduce*",
    "scripts/*", "analysis/*", "notebooks/*.ipynb", "src/*/__main__.py", "dvc.yaml", "main.jl",
]
RUN_HINT = re.compile(
    r"(?im)^\s*(?:\$\s*)?(?:python3?|Rscript|R\s+CMD|bash|sh|make|snakemake|nextflow|julia|"
    r"matlab|docker\s+run|conda\s+(?:env\s+create|activate)|pip\s+install|jupyter|uv\s+run|"
    r"poetry\s+run|quarto\s+render)\b")
USAGE_HEAD = re.compile(r"(?im)^#+\s*(?:usage|how\s+to\s+run|running|quick\s*start|getting\s+started|"
                        r"reproduc\w*|installation|instructions|example)")
SCRIPT_REF = re.compile(r"(?<![\w/.-])([\w./-]+\.(?:py|R|r|sh|m|jl|ipynb|Rmd|nf))\b")


def _files(root: Path, limit: int = 20000):
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git"]
        for f in fns:
            out.append(Path(dp, f).relative_to(root))
            if len(out) >= limit:
                return out
    return out


def scan_dir(path) -> dict:
    root = Path(path)
    files = _files(root)

    def read(name):
        return (root / name).read_text(errors="replace")
    return scan_tree([str(f) for f in files], read)


def scan_tree(file_names, read) -> dict:
    """Checks over a list of repo-relative paths; `read(name)` returns a file's text."""
    files = [Path(f) for f in file_names]
    names = {str(f) for f in files}
    lower = {n.lower(): n for n in names}
    checks = []

    deps = [n for n in names if Path(n).name in DEP_FILES or re.match(r"requirements.*\.txt$", Path(n).name)]
    checks.append({"id": "dependency_file", "passed": bool(deps), "detail": ", ".join(sorted(deps)[:5]) or "none found"})

    readme_name = next((lower[n] for n in sorted(lower) if re.fullmatch(r"readme(\.\w+)?", n)), None)
    readme = read(readme_name) if readme_name else ""
    checks.append({"id": "readme", "passed": bool(readme_name) and len(readme.strip()) > 200,
                   "detail": f"{readme_name} ({len(readme)} chars)" if readme_name else "no top-level README"})

    hints = RUN_HINT.findall(readme)
    has_usage = bool(USAGE_HEAD.search(readme))
    checks.append({"id": "readme_run_steps", "passed": bool(hints),
                   "detail": f"{len(hints)} command line(s)" + (", usage section" if has_usage else "")})

    import fnmatch
    entries = sorted({n for n in names for g in ENTRY_GLOBS if fnmatch.fnmatch(n, g)})
    no_urls = re.sub(r"\w+://\S+|\$\{?[A-Z_]+\}?/\S+|[A-Z_]{3,}/\S+", " ", readme)
    referenced = sorted(set(SCRIPT_REF.findall(no_urls)))
    ref_exist = [r for r in referenced if r.lstrip("./") in names or any(n.endswith("/" + r.lstrip("./")) for n in names)]
    ref_missing = [r for r in referenced if r not in ref_exist and not r.startswith("http")]
    checks.append({"id": "entry_point", "passed": bool(entries or ref_exist),
                   "detail": ", ".join((ref_exist or entries)[:5]) or "no obvious entry point"})
    if ref_missing:
        checks.append({"id": "readme_scripts_exist", "passed": False,
                       "detail": "README mentions missing files: " + ", ".join(ref_missing[:5])})

    lic = [n for n in names if re.match(r"(?i)(licen[cs]e|copying)(\.\w+)?$", n)]
    checks.append({"id": "license_file", "passed": bool(lic), "detail": ", ".join(lic) or "none"})

    ext = {}
    for f in files:
        ext[f.suffix.lower()] = ext.get(f.suffix.lower(), 0) + 1
    return {"n_files": len(files), "top_extensions": sorted(ext.items(), key=lambda x: -x[1])[:6],
            "checks": checks}


def _git(args, cwd, timeout):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def check_repo(clone_url: str, ref: Optional[str] = None, timeout: int = 90) -> dict:
    """Blobless shallow clone (no checkout): only the file list and README are fetched."""
    with tempfile.TemporaryDirectory(prefix="paper-audit-") as td:
        cmd = ["clone", "--depth", "1", "--quiet", "--filter=blob:none", "--no-checkout"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [clone_url, td]
        try:
            p = _git(cmd, None, timeout)
            if p.returncode != 0 and ref:   # ref may be a commit sha or odd tag: retry default branch
                cmd = [c for c in cmd if c not in ("--branch", ref)]
                p = _git(cmd, None, timeout)
            if p.returncode != 0:
                return {"error": "clone failed: " + p.stderr.strip()[:300], "checks": []}
            ls = _git(["ls-tree", "-r", "--name-only", "HEAD"], td, timeout)
            names = [n for n in ls.stdout.splitlines() if n]

            def read(name):
                r = _git(["show", f"HEAD:{name}"], td, timeout)
                return r.stdout if r.returncode == 0 else ""
            out = scan_tree(names, read)
        except subprocess.TimeoutExpired:
            return {"error": f"clone timed out after {timeout}s", "checks": []}
        out["clone_url"], out["ref"] = clone_url, ref
        return out
