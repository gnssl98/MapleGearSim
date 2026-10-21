"""스타포스·잠재 재설정·큐브 사용 기록 조회 (키 소유자 본인 계정 전체 캐릭터).

- 엔드포인트: /maplestory/v1/history/{starforce|potential|cube}, date(KST) 또는 cursor, count 10~1000
- 하루 단위로 조회하고 next_cursor 로 이어서 받는다.
- 지난 날짜는 바뀌지 않으므로 클라이언트 캐시(30일)를 그대로 쓰고, 어제·오늘은 항상 새로 받는다.
- 사용자가 조회 버튼을 누를 때만 호출 (주기적 자동 호출 없음).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.nexon.client import NexonClient

KINDS = ("starforce", "potential", "cube")
MAX_DAYS = 62
PAGE = 1000
FIRST_DAY = {"starforce": date(2023, 12, 27)}


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def fetch_day(client: NexonClient, kind: str, day: date, *, refresh: bool = False) -> list[dict]:
    path = f"/maplestory/v1/history/{kind}"
    out: list[dict] = []
    body = client.get(path, {"count": PAGE, "date": day.isoformat()}, refresh=refresh)
    out += body.get(f"{kind}_history") or []
    while body.get("next_cursor"):
        body = client.get(path, {"count": PAGE, "cursor": body["next_cursor"]}, refresh=refresh)
        out += body.get(f"{kind}_history") or []
    return out


def fetch(start: date, end: date, *, today: date | None = None, client: NexonClient | None = None,
          kinds: tuple[str, ...] = KINDS) -> dict[str, list[dict]]:
    today = today or date.today()
    end = min(end, today)
    if start > end:
        return {k: [] for k in kinds}
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"한 번에 {MAX_DAYS}일까지 조회할 수 있습니다 (API 일일 호출 한도 보호)")
    client = client or NexonClient()
    out: dict[str, list[dict]] = {}
    for kind in kinds:
        rows: list[dict] = []
        for d in _days(max(start, FIRST_DAY.get(kind, start)), end):
            rows += fetch_day(client, kind, d, refresh=d >= today - timedelta(days=1))
        seen = set()
        out[kind] = [r for r in rows if not (r.get("id") in seen or seen.add(r.get("id")))]
    return out
