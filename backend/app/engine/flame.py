"""추가옵션(추옵) 엔진.

방어구/장신구: 급수 = 주스탯 + 부스탯×a + 공격력×b + 올스탯%×c 의 분포를 정확히 계산.
  19종 중 n개를 비복원 균등 추출, 각 옵션 단계는 독립 → (선택 개수, 점수) DP.
무기: "옵션 X 가 단계 ≥ t" 조건들의 동시 만족 확률 (닫힌 형태).
가정: 줄별 단계 독립, 서로 다른 옵션 추출 (리서치 09 에서 확인).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import yaml

from app.paths import GAME_DATA_DIR

ItemType = Literal["armor", "weapon"]


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(GAME_DATA_DIR / "flame.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def tier_distribution(method: str, boss: bool) -> dict[int, float]:
    cfg = load_config()
    bonus = cfg["boss_tier_bonus"] if boss else 0
    return {i + 1 + bonus: p for i, p in enumerate(cfg["methods"][method]["tiers"]) if p > 0}


def option_count_distribution(boss: bool) -> dict[int, float]:
    if boss:
        return {4: 1.0}
    return {i + 1: p for i, p in enumerate(load_config()["option_count_probs"])}


@dataclass
class ScoreCoef:
    main: float = 1
    sub: float = 0.1
    att: float = 4
    all_pct: float = 10


def _option_score_per_tier(opt: str, level: int, boss: bool, main: str, sub: str, attack: str,
                           coef: ScoreCoef) -> float:
    cfg = load_config()
    stat_level = cfg["boss_250_stat_level"] if boss and level >= 250 else level
    single = stat_level // 20 + 1
    dual = level // 40 + 1
    if opt == main:
        return single * coef.main
    if opt == sub:
        return single * coef.sub
    if "+" in opt:
        a, b = opt.split("+")
        return dual * ((coef.main if main in (a, b) else 0) + (coef.sub if sub in (a, b) else 0))
    if opt == attack:
        return cfg["values"]["armor_att_per_tier"] * coef.att
    if opt == "ALL%":
        return cfg["values"]["all_stat_pct_per_tier"] * coef.all_pct
    return 0.0


def score_distribution(level: int, boss: bool, method: str, main: str, sub: str, attack: str = "ATT",
                       coef: ScoreCoef | None = None) -> dict[float, float]:
    """방어구 추옵 급수 분포 {급수: 확률} (1회)."""
    coef = coef or ScoreCoef()
    pool = load_config()["pools"]["armor"]
    tiers = tier_distribution(method, boss)
    per_tier = [_option_score_per_tier(o, level, boss, main, sub, attack, coef) for o in pool]

    # 점수 0 옵션은 하나로 묶어 개수만 센다
    scoring = [s for s in per_tier if s > 0]
    zero_count = len(pool) - len(scoring)

    # dp[k][score] = (선택된 옵션 k개, 점수) 의 가중치 합 (조합 수 × 단계 확률)
    dp: list[dict[float, float]] = [defaultdict(float) for _ in range(5)]
    dp[0][0.0] = 1.0
    for s in scoring:
        for k in range(3, -1, -1):
            for score, w in list(dp[k].items()):
                for t, p in tiers.items():
                    dp[k + 1][round(score + s * t, 4)] += w * p

    result: dict[float, float] = defaultdict(float)
    for n, pn in option_count_distribution(boss).items():
        total_combos = math.comb(len(pool), n)
        for k in range(0, n + 1):
            zeros_needed = n - k
            if zeros_needed > zero_count:
                continue
            ways_zero = math.comb(zero_count, zeros_needed)
            for score, w in dp[k].items():
                result[score] += pn * w * ways_zero / total_combos
    return dict(sorted(result.items()))


def prob_score_at_least(dist: dict[float, float], threshold: float) -> float:
    return sum(p for s, p in dist.items() if s >= threshold - 1e-9)


def weapon_probability(boss: bool, method: str, requirements: dict[str, int]) -> float:
    """무기 추옵: requirements = {옵션: 최소 단계} 를 모두 만족할 확률.
    예) {"ATT": 6} → 공격력 2추 이상, {"ATT": 6, "BOSS%": 6} → 공 2추 + 보공 12%↑ (보스 무기 기준)"""
    pool = load_config()["pools"]["weapon"]
    tiers = tier_distribution(method, boss)
    k = len(requirements)
    p_tiers = 1.0
    for opt, min_tier in requirements.items():
        if opt not in pool:
            raise ValueError(f"무기 추옵 풀에 없는 옵션: {opt}")
        p_tiers *= sum(p for t, p in tiers.items() if t >= min_tier)
    p = 0.0
    for n, pn in option_count_distribution(boss).items():
        if n >= k:
            p += pn * math.comb(len(pool) - k, n - k) / math.comb(len(pool), n)
    return p * p_tiers


def cost_per_attempt(method: str, item_price: float | None = None) -> float:
    m = load_config()["methods"][method]
    if "cost_meso" in m:
        return m["cost_meso"]
    if item_price is None:
        raise ValueError(f"{m['label']} 1개 가격(메소 환산)을 입력하세요")
    return item_price


def weapon_attack_value(base_attack: int, level: int, tier: int, boss: bool) -> int:
    """무기 공/마 추옵 수치. tier 는 최종 단계(보스 3~7, 일반 1~5)."""
    cfg = load_config()["weapon_attack"]
    offset = cfg["boss_exp_offset"] if boss else cfg["normal_exp_offset"]
    pct = (level // 40 + 1) * tier * 1.1 ** (tier - offset)
    return math.ceil(round(base_attack * pct / 100, 6))


def weapon_attack_table(base_attack: int, level: int, boss: bool) -> list[dict]:
    """단계별 무기 공/마 추옵 (높은 단계부터, '1추' = 최고 단계)."""
    tiers = sorted(tier_distribution("meso_reset", boss) | tier_distribution("burning", boss), reverse=True)
    return [{"tier": t, "rank": i + 1, "value": weapon_attack_value(base_attack, level, t, boss)}
            for i, t in enumerate(tiers)]
