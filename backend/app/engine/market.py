"""기록된 매물(시세 기록 CSV)로 시세 추정 + 매물 스펙 → 직작 목표 조건.

경매장 공식 API가 없으므로 "경매장 시세" = 사용자가 기록한 매물의 실구매가(타서버 +10%) 중앙값.
- 완제품 시세: 같은 아이템, 성 ±1, 같은 잠재 등급
- 베이스(노작) 시세: 같은 아이템, 성 0(또는 비움), 잠재 없음/레어
- 되팔기: 같은 조건의 매물 등록가 중앙값 × (1 - 판매 수수료)
최근 30일 기록이 있으면 그것만 쓴다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.engine import potential as pt

RECENT_DAYS = 30
OTHER_WORLD_FEE = 0.10


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def eff_price(row: dict) -> float:
    p = _f(row.get("price_meso")) or 0.0
    return p * (1 + OTHER_WORLD_FEE) if row.get("world_type") == "other" else p


def is_base(row: dict) -> bool:
    return not (_f(row.get("star")) or 0) and (row.get("potential_grade") or "") in ("", "rare")


@dataclass
class Estimate:
    price: float               # 실구매가 중앙값 (판매가 추정이면 등록가 중앙값)
    n: int
    low: float
    high: float
    recent_only: bool
    listing_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__


def _recent(rows: list[dict], now: datetime | None = None) -> tuple[list[dict], bool]:
    now = now or datetime.now()
    out = []
    for r in rows:
        try:
            if now - datetime.fromisoformat(r.get("observed_at", "")) <= timedelta(days=RECENT_DAYS):
                out.append(r)
        except ValueError:
            pass
    return (out, True) if out else (rows, False)


def match(listings: list[dict], item_name: str, *, star: int | None = None, grade: str | None = None,
          base: bool = False, star_tol: int = 1, exclude_id: str | None = None) -> list[dict]:
    out = []
    for r in listings:
        if r.get("id") == exclude_id or (r.get("item_name") or "").strip() != item_name.strip():
            continue
        if not _f(r.get("price_meso")):
            continue
        if base:
            if is_base(r):
                out.append(r)
            continue
        if is_base(r) and (star or 0) > 0:
            continue
        if star is not None and abs((_f(r.get("star")) or 0) - star) > star_tol:
            continue
        if grade is not None and (r.get("potential_grade") or "") != (grade or ""):
            continue
        out.append(r)
    return out


def estimate(rows: list[dict], *, sell: bool = False, now: datetime | None = None) -> Estimate | None:
    if not rows:
        return None
    rows, recent = _recent(rows, now)
    prices = sorted((_f(r["price_meso"]) or 0.0) if sell else eff_price(r) for r in rows)
    return Estimate(statistics.median(prices), len(prices), prices[0], prices[-1], recent,
                    [r.get("id", "") for r in rows])


def finished_price(listings, item_name, star, grade, **kw) -> Estimate | None:
    return estimate(match(listings, item_name, star=star, grade=grade, **kw))


def base_price(listings, item_name, **kw) -> Estimate | None:
    return estimate(match(listings, item_name, base=True, **kw))


def resale(listings: list[dict], item: dict, fee: float) -> tuple[float, Estimate | None, str | None]:
    """현재 장비를 팔 때 손에 쥐는 메소 (수수료 차감). 반환: (금액, 추정, 사유)"""
    if item.get("cuttable_count") == 0:
        return 0.0, None, "가위 0회라 되팔 수 없음"
    est = estimate(match(listings, item["name"], star=item.get("starforce"), grade=item.get("potential_grade")),
                   sell=True)
    if not est:
        return 0.0, None, "기존 장비와 비슷한 매물 기록이 없어 되팔기 0으로 계산"
    return est.price * (1 - fee), est, None


# ---------------------------------------------------------------- 매물 스펙 → 직작 조건


def listing_lines(row: dict, prefix: str) -> list[tuple[str, float]]:
    out = []
    for i in (1, 2, 3):
        text = (row.get(f"{prefix}{i}") or "").strip()
        if text:
            k, v = pt.parse_option(text)
            if k != "OTHER":
                out.append((k, v))
    return out


def conditions_from_lines(lines: list[tuple[str, float]], job: dict) -> list[pt.Condition]:
    """주스탯%(+올스탯%)는 합계 조건, 나머지 유효 옵션은 줄 수 조건으로 (수치는 최소 1줄 등장 기준)."""
    main_keys = {f"{job['main_stat']}%", "ALL%"}
    main_sum = sum(v for k, v in lines if k in main_keys)
    conds = [pt.Condition(sorted(main_keys), main_sum)] if main_sum else []
    counts: dict[str, int] = {}
    for k, _ in lines:
        if k not in main_keys:
            counts[k] = counts.get(k, 0) + 1
    conds += [pt.Condition([k], n, "count") for k, n in counts.items()]
    return conds
