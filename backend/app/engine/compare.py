"""직작 vs 구매 비교: 손익분기, 기대 이득/손해, 손해 확률.

단계(스타포스/잠재/에디/추옵)별 비용 표본을 독립으로 보고 합산한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PCTS = (50, 75, 90, 95, 99)


@dataclass
class StageCost:
    name: str
    expected: float
    samples: np.ndarray


@dataclass
class TradeFees:
    other_world_fee: float = 0.10  # 타월드 구매: 가격의 10% 상당 메이플포인트
    sell_fee: float = 0.05         # 판매 수수료 (MVP 실버+ / 프리미엄PC방 3%)


def sell_fee_rate(mvp: str, pc_room: bool) -> float:
    return 0.03 if mvp in ("silver", "gold", "diamond", "red", "black") or pc_room else 0.05


def effective_buy_price(price: float, other_world: bool, fees: TradeFees | None = None) -> float:
    fees = fees or TradeFees()
    return price * (1 + fees.other_world_fee) if other_world else price


def combine(stages: list[StageCost], n: int = 100_000, seed: int | None = None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    total = np.zeros(n)
    for st in stages:
        if st.samples is None or st.samples.size == 0:
            total += st.expected
        else:
            total += rng.choice(st.samples, size=n, replace=True)
    return total


@dataclass
class CompareResult:
    base_price: float
    craft_expected: float          # 직작 비용 기댓값 (베이스 제외)
    breakeven_price: float          # 완제품 실구매가가 이 값 이상이면 직작이 기대값상 이득
    cumulative_breakeven: list[dict]  # 단계별 누적 손익분기 [{name, expected, cumulative}]
    market_price: float | None      # 완제품 실구매가 (수수료 반영)
    resale_net: float               # 완제품을 사면 팔 수 있는 기존 장비 판매 수령액 (수수료 차감)
    market_net: float | None        # 완제품 실구매가 - 기존 장비 판매 수령액 = 구매 경로 실비용
    expected_profit: float | None   # 양수 = 직작 이득
    loss_probability: float | None  # 직작 총비용이 완제품 실구매가를 넘을 확률
    percentiles: dict[str, float]   # 직작 총비용(베이스 포함) 분포
    histogram: list[dict]


def compare(stages: list[StageCost], base_price: float, market_price: float | None,
            seed: int | None = None, bins: int = 40, resale_net: float = 0.0) -> CompareResult:
    """resale_net: 직작 대상이 '지금 내 장비'일 때, 완제품을 사면 그 장비를 팔 수 있으므로 구매 경로에서 차감."""
    market_net = market_price - resale_net if market_price is not None else None
    craft_e = sum(s.expected for s in stages)
    total = combine(stages, seed=seed) + base_price

    cum, acc = [], base_price
    for s in stages:
        acc += s.expected
        cum.append({"name": s.name, "expected": s.expected, "cumulative": acc})

    hi = float(np.percentile(total, 99))
    lo = float(total.min())
    counts, edges = np.histogram(np.clip(total, lo, hi), bins=bins, range=(lo, max(hi, lo + 1)))

    return CompareResult(
        base_price=base_price,
        craft_expected=craft_e,
        breakeven_price=base_price + craft_e,
        cumulative_breakeven=cum,
        market_price=market_price,
        resale_net=resale_net,
        market_net=market_net,
        expected_profit=(market_net - base_price - craft_e) if market_net is not None else None,
        loss_probability=float((total > market_net).mean()) if market_net is not None else None,
        percentiles={f"p{p}": float(v) for p, v in zip(PCTS, np.percentile(total, PCTS))},
        histogram=[{"lo": float(edges[i]), "hi": float(edges[i + 1]), "count": int(c)} for i, c in enumerate(counts)],
    )
