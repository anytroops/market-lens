"""Shared HTTP client for both platform ingesters.

Responsibilities:
- Polite pacing: a minimum interval between requests per client instance.
- Resilience: exponential backoff with jitter on 429 and 5xx responses and on
  transport errors, honoring Retry-After when present.
- Identification: a normal descriptive user agent from config.
- Raw archiving: every successful response body is written to data/raw/
  BEFORE json parsing, so a parsing bug never requires re-downloading.
  The archive doubles as a cache: a re-run with identical request parameters
  reads from disk and never re-hits the API.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import random
import time
from pathlib import Path
from typing import Any

import httpx

from marketlens.config import HttpConfig

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class BaseClient:
    """HTTP JSON client with rate limiting, retries, and raw-response archiving."""

    def __init__(
        self,
        platform: str,
        base_url: str,
        http_cfg: HttpConfig,
        raw_dir: Path,
    ) -> None:
        self.platform = platform
        self.base_url = base_url.rstrip("/")
        self.cfg = http_cfg
        self.raw_dir = Path(raw_dir) / platform
        self._min_interval = 1.0 / http_cfg.requests_per_second
        self._last_request_at = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": http_cfg.user_agent},
            timeout=http_cfg.timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def _cache_path(self, url: str, params: dict[str, Any]) -> Path:
        canonical = url + "?" + json.dumps(params, sort_keys=True, default=str)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return self.raw_dir / digest[:2] / f"{digest}.json.gz"

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def get_json(self, path: str, params: dict[str, Any] | None = None,
                 cache: bool = True) -> Any:
        """GET a JSON endpoint, archiving the raw body to disk before parsing.

        With cache=True (default), an existing archive for the identical
        request is returned without any network call.
        """
        params = params or {}
        url = path if path.startswith("http") else self.base_url + path
        cache_file = self._cache_path(url, params)

        if cache and cache_file.exists():
            with gzip.open(cache_file, "rt") as f:
                envelope = json.load(f)
            return json.loads(envelope["body"])

        body = self._request_with_retries(url, params)

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "url": url,
            "params": {k: str(v) for k, v in params.items()},
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "body": body,
        }
        tmp = cache_file.with_suffix(".tmp")
        with gzip.open(tmp, "wt") as f:
            json.dump(envelope, f)
        tmp.replace(cache_file)

        return json.loads(body)

    def _request_with_retries(self, url: str, params: dict[str, Any]) -> str:
        """Return the raw response text, retrying on 429/5xx and transport errors."""
        last_error: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            self._throttle()
            try:
                resp = self._client.get(url, params=params)
            except httpx.TransportError as e:
                last_error = e
                self._sleep_backoff(attempt, None)
                continue

            if resp.status_code == 200:
                return resp.text
            if resp.status_code in RETRYABLE_STATUS:
                last_error = httpx.HTTPStatusError(
                    f"{resp.status_code} from {url}", request=resp.request,
                    response=resp,
                )
                self._sleep_backoff(attempt, resp.headers.get("Retry-After"))
                continue
            resp.raise_for_status()

        raise RuntimeError(
            f"giving up on {url} after {self.cfg.max_retries} attempts"
        ) from last_error

    def _sleep_backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = self.cfg.backoff_base_seconds * (self.cfg.backoff_factor ** attempt)
        delay += random.uniform(0, delay / 2)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        log.warning("retrying in %.1fs (attempt %d)", delay, attempt + 1)
        time.sleep(delay)
