"""확률형 BM(캐시 확률형 아이템) 기댓값 · 손익분기.

입력: 공식 확률표(data/game/bm_tables.json) + 사용자가 넣은 1회 가격(원)·현질 금액(원)·아이템별 경매장 가격(메소)
     + 1억 메소당 원 시세(사용자 지정).
- 회수 메소 = Σ (나온 개수 × 경매장 가격 × (1 - 판매 수수료))
- "당첨"으로 고른 아이템 묶음으로 손익분기: N회 중 당첨이 몇 개 나와야 본전인지 + 그럴 확률(이항분포)
- 전체 회수액 분포는 다항분포 몬테카를로로 (본전 확률·분위수)
경매장 가격은 넥슨 오픈 API에 없어 직접 입력하거나 시세 기록 탭 기록을 쓴다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.engine import bm_source

EOK = 1e8


def load_tables() -> dict:
    return bm_source.load()


def find_table(product: str, table: int) -> tuple[dict, dict]:
    for p in load_tables()["products"]:
        if p["id"] == product:
            return p, p["tables"][table]
    raise KeyError(product)


def won_to_meso(won: float, won_per_eok: float) -> float:
    return won / won_per_eok * EOK


def _logpmf(n: int, p: float, ks: np.ndarray) -> np.ndarray:
    lg = np.vectorize(math.lgamma)
    return math.lgamma(n + 1) - lg(ks + 1) - lg(n - ks + 1) + ks * math.log(p) + (n - ks) * math.log1p(-p)


def binom_tail(n: int, p: float, k: int) -> float:
    """P(X ≥ k), X ~ Bin(n, p)"""
    if k <= 0:
        return 1.0
    if k > n or p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return float(min(1.0, np.exp(_logpmf(n, p, np.arange(k, n + 1))).sum()))


def binom_pmf(n: int, p: float, hi: int) -> list[float]:
    """P(X = k), k = 0..min(n, hi)"""
    ks = np.arange(0, min(n, hi) + 1)
    if p <= 0 or p >= 1:
        target = 0 if p <= 0 else n
        return [1.0 if k == target else 0.0 for k in ks]
    return [float(x) for x in np.exp(_logpmf(n, p, ks))]


@dataclass
class Result:
    pulls: int
    spend_won: float
    spend_meso: float
    ev_per_pull: float            # 1회 기대 회수 메소 (수수료 뺀 금액)
    expected: float               # N회 기대 회수 메소
    recovery: float               # 기대 회수율 (회수 ÷ 현질 금액)
    breakeven_price_won: float    # 1회 가격이 이 이하면 기대값상 본전
    jackpot_prob: float           # 1회 당첨 확률
    jackpot_value: float          # 당첨 1개 평균 가치 (수수료 뺀 메소)
    jackpot_expected: float       # N회 당첨 기대 개수
    baseline: float               # 당첨 외 아이템 기대 회수
    need: int | None              # 본전에 필요한 당첨 개수 (불가능하면 None)
    need_prob: float | None       # 그만큼 이상 당첨될 확률
    pmf: list[float] = field(default_factory=list)  # 당첨 개수 분포 (0..)
    profit_prob: float = 0.0      # 몬테카를로: 회수 ≥ 현질 금액
    percentiles: dict[str, float] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)  # 아이템별 기여
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__


def evaluate(rows: list[dict], values: dict[str, float], jackpots: set[str], unit_price_won: float,
             spend_won: float, won_per_eok: float, fee: float, trials: int = 20000, seed: int = 7) -> Result:
    """rows: [{item, prob}], values: 아이템 → 경매장 가격(메소, 수수료 전)"""
    if unit_price_won <= 0 or won_per_eok <= 0:
        raise ValueError("1회 가격과 1억 메소당 원 시세를 넣어 주세요")
    n = int(spend_won // unit_price_won)  # 묶음가 ÷ 개수가 나누어떨어지지 않을 때를 위해 호출부에서 아주 작은 여유를 더함
    spend_meso = won_to_meso(round(n * unit_price_won, 2), won_per_eok)
    probs = np.array([r["prob"] for r in rows], dtype=float)
    net = np.array([max(0.0, values.get(r["item"], 0.0)) * (1 - fee) for r in rows])
    warnings = []
    total = probs.sum()
    if abs(total - 1) > 0.005:
        warnings.append(f"확률 합이 {total * 100:.2f}% 입니다 (표기 반올림 또는 표 일부)")
    ev = float(probs @ net)
    jk = np.array([r["item"] in jackpots for r in rows])
    pj = float(probs[jk].sum())
    vj = float((probs[jk] @ net[jk]) / pj) if pj > 0 else 0.0
    base = n * float(probs[~jk] @ net[~jk])
    need = need_prob = None
    if pj > 0 and vj > 0:
        need = max(0, math.ceil((spend_meso - base) / vj - 1e-9))
        need_prob = binom_tail(n, pj, need) if need <= n else 0.0
        if need > n:
            warnings.append("당첨만으로는 본전이 불가능한 금액입니다 (모든 회차가 당첨이어도 부족)")
    mean_j = n * pj
    hi = int(max(need or 0, mean_j + 4 * math.sqrt(max(mean_j, 1))) + 2)
    pmf = binom_pmf(n, pj, min(hi, 200)) if n else [1.0]

    # 몬테카를로: 가치가 있는 아이템만 따로, 나머지는 하나로 묶어 다항분포 표본
    valued = net > 0
    pct, profit = {}, 0.0
    if n and valued.any():
        cats = np.append(probs[valued], max(0.0, 1 - probs[valued].sum()))
        cats = cats / cats.sum()
        counts = np.random.default_rng(seed).multinomial(n, cats, size=trials)
        ret = counts[:, :-1] @ net[valued]
        profit = float((ret >= spend_meso).mean())
        pct = {k: float(np.percentile(ret, q)) for k, q in (("p10", 10), ("p50", 50), ("p90", 90), ("p99", 99))}
    contrib = [{"item": r["item"], "group": r.get("group", ""), "prob": r["prob"], "value": values.get(r["item"], 0.0),
                "ev": float(r["prob"] * net[i]), "jackpot": bool(jk[i])} for i, r in enumerate(rows)]
    return Result(
        pulls=n, spend_won=round(n * unit_price_won, 2), spend_meso=spend_meso, ev_per_pull=ev, expected=n * ev,
        recovery=(n * ev / spend_meso) if spend_meso else 0.0,
        breakeven_price_won=ev / EOK * won_per_eok, jackpot_prob=pj, jackpot_value=vj, jackpot_expected=mean_j,
        baseline=base, need=need, need_prob=need_prob, pmf=pmf, profit_prob=profit, percentiles=pct,
        rows=contrib, warnings=warnings)
