"""One HTTP client for every source: retries, per-host throttle, fixture mode.

Fixture mode (MOONAPE_FIXTURE=1) serves recorded responses from tests/fixtures/<fixture>.{json,csv,txt}
instead of touching the network, so the whole pipeline runs in CI and before any key exists.
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from moonape import config

log = logging.getLogger("moonape.http")

DEFAULT_UA = "moonape/0.1 (+https://github.com/hanxa-xyz/moonape)"

# seconds between requests to the same host
HOST_MIN_INTERVAL = {
    "data.sec.gov": 0.12,
    "www.sec.gov": 0.12,
    "efts.sec.gov": 0.12,
    "oauth.reddit.com": 0.65,
    "www.reddit.com": 0.65,
    "arctic-shift.photon-reddit.com": 2.5,
    "query1.finance.yahoo.com": 1.2,
    "query2.finance.yahoo.com": 1.2,
    "api.stlouisfed.org": 0.55,
    "api.twitterapi.io": 0.5,
    "www.trumpstruth.org": 1.0,
    "online.fliphtml5.com": 1.2,
    "data.alpaca.markets": 0.31,
    "paper-api.alpaca.markets": 0.31,
    "api.alpaca.markets": 0.31,
}


class FixtureMissing(FileNotFoundError):
    pass


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status = status
        self.url = url


@dataclass
class FixtureResponse:
    path: Path
    status_code: int = 200

    @property
    def content(self) -> bytes:
        return self.path.read_bytes()

    @property
    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def json(self):
        return json.loads(self.text)

    @property
    def headers(self):
        return {}


class Http:
    def __init__(self, fixture: bool | None = None, timeout: float = 30.0):
        self.fixture = config.fixture_mode() if fixture is None else fixture
        self._client = httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": DEFAULT_UA})
        self._last_call: dict[str, float] = {}

    # --- fixtures ---------------------------------------------------------------------------------
    def _fixture(self, name: str) -> FixtureResponse:
        base = config.FIXTURES / name
        for ext in ("", ".json", ".csv", ".txt", ".xml", ".js"):
            p = Path(str(base) + ext)
            if p.is_file():
                return FixtureResponse(p)
        raise FixtureMissing(f"no fixture for {name!r} under {config.FIXTURES}")

    # --- throttle + retry -------------------------------------------------------------------------
    def _throttle(self, url: str):
        host = urlsplit(url).netloc
        gap = HOST_MIN_INTERVAL.get(host, 0.0)
        if gap:
            wait = self._last_call.get(host, 0.0) + gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        self._last_call[host] = time.monotonic()

    def request(self, method: str, url: str, *, params=None, headers=None, data=None, auth=None,
                fixture: str | None = None, retries: int = 4, ok_404: bool = False):
        if self.fixture:
            if fixture is None:
                raise FixtureMissing(f"fixture mode but no fixture name given for {url}")
            return self._fixture(fixture)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            self._throttle(url)
            try:
                r = self._client.request(method, url, params=params, headers=headers, data=data, auth=auth)
            except httpx.TransportError as e:  # DNS, timeouts, resets
                last_exc = e
                log.warning("transport error %s (%s); retry %d", url, e, attempt)
                time.sleep(min(60, 2**attempt + random.random()))
                continue
            if r.status_code == 404 and ok_404:
                return r
            slow_down = r.status_code == 422 and "slow down" in r.text.lower()  # Arctic Shift's query-timeout answer
            if (r.status_code in (429, 500, 502, 503, 504) or slow_down) and attempt < retries:
                retry_after = r.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else min(90, (8 if slow_down else 3) * 2**attempt + random.random())
                log.warning("HTTP %s %s; sleeping %.1fs", r.status_code, url, wait)
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise HttpError(r.status_code, str(r.url), r.text)
            return r
        raise HttpError(0, url, f"gave up after {retries} retries: {last_exc}")

    def get(self, url: str, **kw):
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw):
        return self.request("POST", url, **kw)

    def get_json(self, url: str, **kw):
        return self.get(url, **kw).json()

    def close(self):
        self._client.close()
