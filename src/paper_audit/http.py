"""Tiny HTTP layer with optional record/replay so tests never touch the network.

PAPER_AUDIT_RECORD=<dir>  save every response under <dir>
PAPER_AUDIT_REPLAY=<dir>  serve responses only from <dir>; missing => offline error
PAPER_AUDIT_CACHE=<dir>   read-through cache: serve from <dir> if present, else fetch + save
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import warnings

warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL.*")  # macOS system Python 3.9
import requests  # noqa: E402

UA = "paper-repro-auditor/0.1 (+https://github.com/; reproducibility audit; mailto:none)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 15        # connect/read timeout per socket operation
MAX_SECONDS = 60    # hard cap on downloading one body


@dataclass
class Resp:
    url: str          # final URL after redirects
    status: int       # 0 = network error / offline
    content: bytes
    content_type: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content or b"null")


class OfflineError(RuntimeError):
    pass


_session = requests.Session()


def _key(method: str, url: str, headers: Optional[dict]) -> str:
    hs = sorted((k, v) for k, v in (headers or {}).items() if k.lower() != "authorization")
    h = hashlib.sha1(f"{method} {url} {hs}".encode()).hexdigest()[:16]
    return h


def _store_dir(var: str) -> Optional[Path]:
    v = os.environ.get(var)
    return Path(v) if v else None


def _load(d: Path, k: str) -> Optional[Resp]:
    meta = d / f"{k}.json"
    if not meta.exists():
        return None
    m = json.loads(meta.read_text())
    body = (d / f"{k}.bin").read_bytes() if (d / f"{k}.bin").exists() else b""
    return Resp(m["url"], m["status"], body, m.get("content_type", ""), m.get("error", ""))


def _save(d: Path, k: str, req_url: str, r: Resp) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{k}.json").write_text(json.dumps(
        {"request": req_url, "url": r.url, "status": r.status,
         "content_type": r.content_type, "error": r.error}, indent=1))
    (d / f"{k}.bin").write_bytes(r.content)


def request(url: str, method: str = "GET", headers: Optional[dict] = None,
            max_bytes: int = 40_000_000, browser: bool = False, retry: bool = True) -> Resp:
    """GET/HEAD a URL with one retry on network errors / 5xx / 429. Never raises for HTTP errors."""
    cache = _store_dir("PAPER_AUDIT_CACHE")
    if cache is not None:
        hit = _load(cache, _key(method, url, headers))
        if hit is not None and hit.status != 0:
            return hit
    r = _request(url, method, headers, max_bytes, browser)
    if retry and (r.status == 0 or r.status >= 500 or r.status == 429):
        if os.environ.get("PAPER_AUDIT_REPLAY") is None:
            time.sleep(2)
            r = _request(url, method, headers, max_bytes, browser)
    if cache is not None:
        _save(cache, _key(method, url, headers), url, r)
    return r


def _request(url: str, method: str = "GET", headers: Optional[dict] = None,
            max_bytes: int = 40_000_000, browser: bool = False) -> Resp:
    """GET/HEAD a URL. Never raises for HTTP/network errors (status=0 instead)."""
    k = _key(method, url, headers)
    replay = _store_dir("PAPER_AUDIT_REPLAY")
    if replay is not None:
        r = _load(replay, k)
        if r is None:
            raise OfflineError(f"no recorded response for {method} {url}")
        return r
    h = {"User-Agent": BROWSER_UA if browser else UA}
    h.update(headers or {})
    try:
        with _session.request(method, url, headers=h, timeout=TIMEOUT,
                              allow_redirects=True, stream=True) as resp:
            body = b""
            if method != "HEAD":
                chunks = []
                size = 0
                t0 = time.monotonic()
                for c in resp.iter_content(65536):
                    chunks.append(c)
                    size += len(c)
                    if size > max_bytes or time.monotonic() - t0 > MAX_SECONDS:
                        break
                body = b"".join(chunks)
            r = Resp(resp.url, resp.status_code, body, resp.headers.get("content-type", ""))
    except requests.RequestException as e:
        r = Resp(url, 0, b"", "", f"{type(e).__name__}: {e}"[:300])
    rec = _store_dir("PAPER_AUDIT_RECORD")
    if rec is not None:
        _save(rec, k, url, r)
    return r


def get_json(url: str, headers: Optional[dict] = None):
    r = request(url, headers=headers)
    if not r.ok:
        return None
    try:
        return r.json()
    except ValueError:
        return None
