"""스타포스 기대 비용 엔진.

모델(docs/research/03_starforce.md §7):
- 상태 = 현재 성급. 성공 → s+1 (1+1 이벤트 시 s+2), 실패 → 유지, 파괴 → 복구 성급 r(s).
- 기댓값은 흡수 마르코프 체인의 연립방정식 (I - Q) x = r 로 계산.
- 분포(백분위)는 벡터화 몬테카를로.
- 파괴방지/복구 방식 최적 정책은 정책 반복(policy iteration).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Literal

import numpy as np
import yaml

from app.paths import GAME_DATA_DIR

RecoveryMode = Literal["basic", "restore"]
MvpGrade = Literal["none", "bronze", "silver", "gold", "diamond", "red", "black"]


@lru_cache(maxsize=1)
def load_table() -> dict:
    with open(GAME_DATA_DIR / "starforce.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def max_star_for_level(level: int, table: dict | None = None) -> int:
    table = table or load_table()
    result = 0
    for row in table["max_star_by_level"]:
        if level >= row["min_level"]:
            result = row["max_star"]
    return result


def base_cost(level: int, star: int, table: dict | None = None) -> int:
    """할인 전 1회 강화 비용 (100메소 단위 반올림)."""
    table = table or load_table()
    cost_cfg = table["cost"]
    if star <= cost_cfg["low"]["max_star"]:
        e, d = cost_cfg["low"]["exponent"], cost_cfg["low"]["divisor"]
    else:
        e, d = cost_cfg["high_exponent"], cost_cfg["high_divisor"][star]
    raw = 1000 + level**3 * (star + 1) ** e / d
    return int(round(raw / 100.0)) * 100


def actual_probs(star: int, table: dict | None = None) -> tuple[float, float]:
    """스타캐치 상시 적용 후 (성공, 파괴) 확률."""
    table = table or load_table()
    p = table["base_success"][star] / 100
    d = table["base_destroy"][star] / 100
    succ = min(1.0, p * table["catch_multiplier"])
    dest = d * (1 - succ) / (1 - p) if p < 1 else 0.0
    return succ, dest


@dataclass
class Events:
    discount30: bool = False
    destroy_reduction: bool = False
    guaranteed_5_10_15: bool = False
    plus_one: bool = False
    recovery_discount: bool = False

    @classmethod
    def shining(cls) -> "Events":
        return cls(discount30=True, destroy_reduction=True)


@dataclass
class StarforceInput:
    level: int
    start: int
    target: int
    mvp: MvpGrade = "none"
    pc_room: bool = False
    mvp_max_star: int | None = None
    events: Events = field(default_factory=Events)
    safeguard: frozenset[int] = frozenset()
    # 파괴 시점 성급별 복구 방식. 미지정은 basic(12성).
    recovery: dict[int, RecoveryMode] = field(default_factory=dict)
    spare_price: float = 0.0  # 동일 장비(스페어) 1개 시세 (메소)


@dataclass
class Policy:
    safeguard: frozenset[int]
    recovery: dict[int, RecoveryMode]


@dataclass
class StepInfo:
    star: int
    success: float
    fail: float
    destroy: float
    cost: float  # 할인·파방 반영 1회 비용
    next_star: int
    recovery_star: int
    recovery_spares: int
    recovery_meso: float


def _discount_factor(inp: StarforceInput, table: dict, star: int) -> float:
    t = table["discount"]
    mvp_max = inp.mvp_max_star if inp.mvp_max_star is not None else t["mvp_max_star_default"]
    rate = 0.0
    if star <= mvp_max:
        rate += t["mvp_rate"][inp.mvp] + (t["pc_room_rate"] if inp.pc_room else 0.0)
    factor = 1 - rate
    if inp.events.discount30:
        factor *= 1 - t["event_discount"]
    return factor


def make_step(inp: StarforceInput, table: dict, s: int) -> StepInfo:
    """현재 성급 s에서의 1회 시도 전이·비용."""
    t, ev = table, inp.events
    succ, dest = actual_probs(s, t)
    if ev.guaranteed_5_10_15 and s in t["events"]["guaranteed_stars"]:
        succ, dest = 1.0, 0.0
    if ev.destroy_reduction and s <= t["events"]["destroy_reduction"]["max_star"]:
        dest *= t["events"]["destroy_reduction"]["multiplier"]

    bc = base_cost(inp.level, s, t)
    cost = bc * _discount_factor(inp, t, s)
    if s in inp.safeguard and s in t["safeguard"]["stars"] and dest > 0:
        dest = 0.0
        cost += bc * t["safeguard"]["extra_cost_ratio"]

    step = 2 if ev.plus_one and s <= t["events"]["plus_one_max_star"] else 1
    next_star = min(s + step, inp.target)

    rec = t["recovery"]
    r_restore = min(s, rec["max_restore_star"])
    if inp.recovery.get(s, "basic") == "restore" and r_restore in rec["restore"]:
        info = rec["restore"][r_restore]
        r_star, spares = r_restore, info["spares"]
        table_row = rec.get("restore_meso_table_eok", {}).get(inp.level)
        meso = table_row[r_restore] * 1e8 if table_row else info["meso_coef"] * inp.level**3
        if ev.recovery_discount:
            meso *= 1 - t["events"]["recovery_meso_discount"]
    else:
        r_star, spares, meso = rec["basic_star"], 1, 0.0

    return StepInfo(s, succ, 1 - succ - dest, dest, cost, next_star, r_star, spares, meso)


class Chain:
    """주어진 입력/정책에 대한 성급별 전이·비용 테이블."""

    def __init__(self, inp: StarforceInput, table: dict | None = None):
        self.table = table or load_table()
        self.inp = inp
        max_star = max_star_for_level(inp.level, self.table)
        if not (0 <= inp.start < inp.target <= max_star):
            raise ValueError(f"성급 범위 오류: start={inp.start}, target={inp.target}, max={max_star}")
        self.n = inp.target  # 과도 상태 0..target-1
        self.steps = [make_step(inp, self.table, s) for s in range(self.n)]

    def matrix(self) -> np.ndarray:
        """I - Q (과도 상태 간 전이)."""
        a = np.eye(self.n)
        for st in self.steps:
            a[st.star, st.star] -= st.fail
            if st.next_star < self.n:
                a[st.star, st.next_star] -= st.success
            if st.destroy > 0:
                a[st.star, st.recovery_star] -= st.destroy
        return a

    def solve(self, reward: np.ndarray) -> np.ndarray:
        return np.linalg.solve(self.matrix(), reward)

    def rewards(self) -> dict[str, np.ndarray]:
        sp = self.inp.spare_price
        return {
            "meso": np.array([st.cost + st.destroy * st.recovery_meso for st in self.steps]),
            "attempts": np.ones(self.n),
            "destroys": np.array([st.destroy for st in self.steps]),
            "spares": np.array([st.destroy * st.recovery_spares for st in self.steps]),
            "total": np.array(
                [st.cost + st.destroy * (st.recovery_meso + st.recovery_spares * sp) for st in self.steps]
            ),
        }


@dataclass
class Expectation:
    meso: float
    attempts: float
    destroys: float
    spares: float
    total: float  # meso + spares × 스페어 시세


def expected(inp: StarforceInput, table: dict | None = None) -> tuple[Expectation, Chain]:
    chain = Chain(inp, table)
    vals = {k: float(chain.solve(r)[inp.start]) for k, r in chain.rewards().items()}
    return Expectation(**vals), chain


def with_policy(inp: StarforceInput, pol: Policy) -> StarforceInput:
    return replace(inp, safeguard=pol.safeguard, recovery=pol.recovery)


def optimize_policy(inp: StarforceInput, table: dict | None = None, max_iter: int = 100) -> Policy:
    """총비용(메소 + 스페어 가치) 기댓값을 최소화하는 파괴방지/복구 정책 (정책 반복)."""
    table = table or load_table()
    sg_stars = {s for s in table["safeguard"]["stars"] if s < inp.target}
    policy = Policy(frozenset(), {})

    for _ in range(max_iter):
        chain = Chain(with_policy(inp, policy), table)
        v_ext = np.append(chain.solve(chain.rewards()["total"]), 0.0)  # index target → 0

        new_sg, new_rec = set(), {}
        for s in range(inp.target):
            can_destroy = actual_probs(s, table)[1] > 0
            best = None
            for sg in ([False, True] if s in sg_stars and can_destroy else [False]):
                for mode in (["basic", "restore"] if can_destroy else ["basic"]):
                    trial = Policy(frozenset({s} if sg else ()), {s: mode})
                    st = make_step(with_policy(inp, trial), table, s)
                    q = (
                        st.cost
                        + st.success * v_ext[st.next_star]
                        + st.destroy * (st.recovery_meso + st.recovery_spares * inp.spare_price + v_ext[st.recovery_star])
                    ) / (st.success + st.destroy)
                    if best is None or q < best[0] - 1e-6:
                        best = (q, sg, mode)
            if best[1]:
                new_sg.add(s)
            if best[2] == "restore":
                new_rec[s] = "restore"
        new_policy = Policy(frozenset(new_sg), new_rec)
        if new_policy == policy:
            break
        policy = new_policy
    return policy


@dataclass
class Distribution:
    trials: int
    completed: int
    percentiles: dict[str, float]  # 총비용 기준 p50/p75/p90/p95/p99
    meso_percentiles: dict[str, float]
    destroy_percentiles: dict[str, float]
    no_destroy_prob: float
    histogram: list[dict]  # [{lo, hi, count}]
    mean_total: float
    samples: np.ndarray | None = field(default=None, repr=False)  # 완료된 시행의 총비용


PCTS = (50, 75, 90, 95, 99)


def simulate(chain: Chain, trials: int = 100_000, seed: int | None = None, time_limit: float = 5.0,
             bins: int = 40) -> Distribution:
    inp = chain.inp
    n = chain.n
    succ = np.array([st.success for st in chain.steps])
    dest_cum = succ + np.array([st.destroy for st in chain.steps])
    cost = np.array([st.cost for st in chain.steps])
    nxt = np.array([st.next_star for st in chain.steps])
    rec = np.array([st.recovery_star for st in chain.steps])
    rec_meso = np.array([st.recovery_meso for st in chain.steps])
    rec_spares = np.array([st.recovery_spares for st in chain.steps])

    rng = np.random.default_rng(seed)
    state = np.full(trials, inp.start, dtype=np.int64)
    meso = np.zeros(trials)
    spares = np.zeros(trials)
    destroys = np.zeros(trials, dtype=np.int64)
    active = np.arange(trials)
    t0 = time.perf_counter()

    while active.size and time.perf_counter() - t0 < time_limit:
        s = state[active]
        u = rng.random(active.size)
        meso[active] += cost[s]
        is_succ = u < succ[s]
        is_dest = ~is_succ & (u < dest_cum[s])
        new = s.copy()
        new[is_succ] = nxt[s[is_succ]]
        d_idx = active[is_dest]
        d_star = s[is_dest]
        new[is_dest] = rec[d_star]
        meso[d_idx] += rec_meso[d_star]
        spares[d_idx] += rec_spares[d_star]
        destroys[d_idx] += 1
        state[active] = new
        active = active[new < n]

    done = np.ones(trials, dtype=bool)
    done[active] = False
    total = meso + spares * inp.spare_price
    t_done, m_done, d_done = total[done], meso[done], destroys[done]

    def pct(arr: np.ndarray) -> dict[str, float]:
        if arr.size == 0:
            return {f"p{p}": float("nan") for p in PCTS}
        return {f"p{p}": float(v) for p, v in zip(PCTS, np.percentile(arr, PCTS))}

    hist = []
    if t_done.size:
        hi = float(np.percentile(t_done, 99))
        lo = float(t_done.min())
        if hi <= lo:
            hi = lo + 1
        counts, edges = np.histogram(np.clip(t_done, lo, hi), bins=bins, range=(lo, hi))
        hist = [{"lo": float(edges[i]), "hi": float(edges[i + 1]), "count": int(c)} for i, c in enumerate(counts)]

    return Distribution(
        trials=trials,
        completed=int(done.sum()),
        percentiles=pct(t_done),
        meso_percentiles=pct(m_done),
        destroy_percentiles=pct(d_done.astype(float)),
        no_destroy_prob=float((d_done == 0).mean()) if d_done.size else float("nan"),
        histogram=hist,
        mean_total=float(t_done.mean()) if t_done.size else float("nan"),
        samples=t_done,
    )
