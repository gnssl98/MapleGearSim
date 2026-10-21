"""MVP 작 비교: 다음 MVP 등급까지 모자란 금액을 어떤 방법으로 채우면 실질 비용이 가장 적은가.

실질 비용(원) = 채울 금액 − 회수 가치(원) − MVP 혜택 가치(원)
- 회수: 메소마켓(메이플포인트→메소)은 회수율을 사용자 지정(기본 100%), 확률형 BM은 기댓값 회수율(engine/bm.py),
        치장 캐시템은 0
- 혜택: 스타포스 할인(1~17성 강화 메소 × 할인율) + 경매장 판매 수수료 감소(판매액 × 수수료 차이) + 기타(원, 직접 입력)
  비교 기준은 추가 결제 없이 유지되는 등급(현재 13주 누적 금액 기준).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from app.paths import GAME_DATA_DIR

EOK = 1e8


@lru_cache(maxsize=1)
def load_grades() -> dict:
    with open(GAME_DATA_DIR / "mvp.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def grade_for(cash: float) -> dict | None:
    out = None
    for g in load_grades()["grades"]:
        if cash >= g["cash"]:
            out = g
    return out


def benefit_meso(grade: dict | None, sf_meso: float, sell_meso: float) -> float:
    none_fee = load_grades()["none_sell_fee"]
    if not grade:
        return 0.0
    return grade["starforce"] * sf_meso + (none_fee - grade["sell_fee"]) * sell_meso


@dataclass
class Option:
    label: str
    recovery: float          # 결제 금액 대비 회수 가치 비율 (원 기준)
    kind: str = "custom"     # mesomarket | bm | cash | custom
    note: str = ""
    pay: float | None = None  # 실제 결제액 (확률형은 1회 단위로 올림, 없으면 모자란 금액)


def compare(current_cash: float, target: str, sf_meso: float, sell_meso: float, other_won: float,
            won_per_eok: float, options: list[Option]) -> dict:
    grades = {g["id"]: g for g in load_grades()["grades"]}
    tg = grades[target]
    base = grade_for(current_cash)
    need = max(0.0, tg["cash"] - current_cash)
    gain_meso = benefit_meso(tg, sf_meso, sell_meso) - benefit_meso(base, sf_meso, sell_meso)
    gain_won = gain_meso / EOK * won_per_eok + (other_won if need > 0 or base is None or base["id"] != target else 0)
    rows = []
    for o in options:
        pay = need if o.pay is None else o.pay
        recovered = pay * o.recovery
        net = pay - recovered - gain_won
        rows.append({"label": o.label, "kind": o.kind, "note": o.note, "recovery": o.recovery, "pay": pay,
                     "recovered_won": recovered, "recovered_meso": recovered / won_per_eok * EOK,
                     "net_cost": net})
    rows.sort(key=lambda r: r["net_cost"])
    return {"need": need, "base": base, "target": tg, "benefit_meso": gain_meso, "benefit_won": gain_won,
            "rows": rows, "skip_cost": 0.0}
