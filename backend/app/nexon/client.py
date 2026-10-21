"""넥슨 오픈 API 클라이언트.

- 키: 환경변수 NEXON_API_KEY 또는 프로젝트 루트 .env (로컬 전용, 외부 전송 금지 — 약관 제5조)
- 레이트 리밋: 개발 키 초당 5회 → 0.25초 간격으로 직렬 호출
- 캐시: data/cache/nexon/ (사용자 PC에만 보관, 30일 초과분은 재조회 — 약관/운영정책)
- 주기적 자동 호출 없음: 사용자가 새로고침할 때만 호출 (약관 제5조 ⑧)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from app.paths import DATA_DIR, ROOT_DIR

BASE_URL = "https://open.api.nexon.com"
CACHE_DIR = DATA_DIR / "cache" / "nexon"
MIN_INTERVAL_SEC = 0.25
MAX_CACHE_AGE_SEC = 30 * 24 * 3600


class NexonApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"[{status} {code}] {message}")
        self.status, self.code = status, code


def load_api_key() -> str | None:
    if os.environ.get("NEXON_API_KEY"):
        return os.environ["NEXON_API_KEY"]
    env = ROOT_DIR / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("NEXON_API_KEY="):
                return line.split("=", 1)[1].strip() or None
    return None


class NexonClient:
    _lock = threading.Lock()
    _last_call = 0.0

    def __init__(self, api_key: str | None = None, cache_dir: Path = CACHE_DIR):
        self.api_key = api_key or load_api_key()
        self.cache_dir = cache_dir

    def _cache_path(self, path: str, params: dict) -> Path:
        key = path + "?" + urllib.parse.urlencode(sorted(params.items()))
        digest = hashlib.sha1(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{path.strip('/').replace('/', '_')}_{digest}.json"

    def get(self, path: str, params: dict | None = None, *, refresh: bool = False) -> dict:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        cache = self._cache_path(path, params)
        if not refresh and cache.exists() and time.time() - cache.stat().st_mtime < MAX_CACHE_AGE_SEC:
            return json.loads(cache.read_text(encoding="utf-8"))
        if not self.api_key:
            raise NexonApiError(401, "NO_KEY", "넥슨 오픈 API 키가 없습니다 (.env 의 NEXON_API_KEY)")

        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"x-nxopen-api-key": self.api_key, "accept": "application/json"})
        with NexonClient._lock:
            wait = MIN_INTERVAL_SEC - (time.monotonic() - NexonClient._last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode("utf-8")).get("error", {})
                except Exception:
                    err = {}
                raise NexonApiError(e.code, err.get("name", "HTTP"), err.get("message", str(e))) from e
            finally:
                NexonClient._last_call = time.monotonic()

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body

    def ocid(self, character_name: str, *, refresh: bool = False) -> str:
        return self.get("/maplestory/v1/id", {"character_name": character_name}, refresh=refresh)["ocid"]


def clear_cache() -> int:
    """약관 제11조 ③ 대비: 캐시된 결과 데이터 일괄 삭제."""
    n = 0
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
            n += 1
    return n
