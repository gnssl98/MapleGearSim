"""직작 계산 API: 스타포스 / 잠재 / 에디 / 추옵 / 종합(손익분기)."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import store
from app.engine import compare as cmp
from app.engine import flame as fl
from app.engine import potential as pt
from app.engine import starforce as sf

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ 스타포스


class EventsModel(BaseModel):
    discount30: bool = False
    destroy_reduction: bool = False
    guaranteed_5_10_15: bool = False
    plus_one: bool = False
    recovery_discount: bool = False


class StarforceReq(BaseModel):
    level: int = Field(ge=0, le=300)
    start: int = Field(ge=0, le=29)
    target: int = Field(ge=1, le=30)
    mvp: Literal["none", "bronze", "silver", "gold", "diamond", "red", "black"] = "none"
    pc_room: bool = False
    mvp_max_star: int | None = None
    events: EventsModel = EventsModel()
    safeguard: list[int] = []
    recovery: dict[int, Literal["basic", "restore"]] = {}
    spare_price: float = 0
    optimize: bool = False
    trials: int = Field(default=100_000, ge=1_000, le=500_000)


def _sf_input(req: StarforceReq, policy: sf.Policy | None = None) -> sf.StarforceInput:
    return sf.StarforceInput(
        level=req.level, start=req.start, target=req.target, mvp=req.mvp, pc_room=req.pc_room,
        mvp_max_star=req.mvp_max_star, events=sf.Events(**req.events.model_dump()),
        safeguard=policy.safeguard if policy else frozenset(req.safeguard),
        recovery=policy.recovery if policy else dict(req.recovery),
        spare_price=req.spare_price,
    )


def _dist_dict(d) -> dict:
    return {k: v for k, v in d.__dict__.items() if k != "samples"}


def run_starforce(req: StarforceReq) -> tuple[dict, np.ndarray, float]:
    policy = sf.optimize_policy(_sf_input(req)) if req.optimize else None
    inp = _sf_input(req, policy)
    try:
        exp, chain = sf.expected(inp)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    dist = sf.simulate(chain, trials=req.trials)
    remaining = {k: chain.solve(r) for k, r in chain.rewards().items()}
    table = sf.load_table()
    steps = [
        {
            **st.__dict__,
            "expected_total_from_here": float(remaining["total"][st.star]),
            "safeguard": st.star in inp.safeguard,
            "recovery_mode": inp.recovery.get(st.star, "basic"),
            "unverified_cost": st.star in table["unverified_cost_stars"],
        }
        for st in chain.steps[req.start:]
    ]
    warnings = []
    if any(s["unverified_cost"] for s in steps):
        warnings.append("23성 이상 1회 비용 공식(제수 200)은 미검증입니다.")
    if (any(inp.recovery.get(s) == "restore" for s in range(req.start, req.target))
            and req.level not in table["recovery"].get("restore_meso_table_eok", {})):
        warnings.append("이 레벨의 확정 복구 메소는 L³ 비례 근사치입니다 (160/200/250제는 표 값).")
    if req.spare_price == 0 and exp.destroys > 0.01:
        warnings.append(f"스페어(노작) 시세가 0이라 기대 파괴 {exp.destroys:.2f}회의 스페어 비용이 빠져 있습니다.")
    if dist.completed < dist.trials:
        warnings.append(f"시뮬레이션 시간 제한으로 {dist.trials - dist.completed}회 미완료 (분포는 완료분 기준).")
    result = {
        "expected": exp.__dict__,
        "distribution": _dist_dict(dist),
        "steps": steps,
        "policy": {"safeguard": sorted(inp.safeguard), "recovery": {str(k): v for k, v in inp.recovery.items()}}
        if req.optimize else None,
        "table_version": table["version"],
        "warnings": warnings,
    }
    return result, dist.samples, exp.total


@router.post("/starforce")
def starforce(req: StarforceReq):
    return run_starforce(req)[0]


# ------------------------------------------------------------------ 잠재 / 에디


class ConditionModel(BaseModel):
    keys: list[str]
    min: float
    mode: Literal["sum", "count"] = "sum"


class PotentialReq(BaseModel):
    kind: Literal["potential", "additional"] = "potential"
    part: str
    level: int
    current: Literal["rare", "epic", "unique", "legendary"] = "legendary"
    target_grade: Literal["rare", "epic", "unique", "legendary"] = "legendary"
    job: str = "adele"
    preset_id: str | None = None
    conditions: list[ConditionModel] = []
    pity_used: dict[str, int] = {}
    miracle: bool = False


def run_potential(req: PotentialReq) -> tuple[dict, np.ndarray, float]:
    conds = [pt.Condition(**c.model_dump()) for c in req.conditions]
    label = None
    if req.preset_id:
        match = [p for p in pt.presets(req.job, req.part, req.kind, req.level) if p["id"] == req.preset_id]
        if not match:
            raise HTTPException(400, f"프리셋 없음: {req.preset_id}")
        conds, label = match[0]["conditions"], match[0]["label"]
    if pt.GRADES.index(req.current) > pt.GRADES.index(req.target_grade):
        raise HTTPException(400, "현재 등급이 목표 등급보다 높습니다")
    try:
        r = pt.calculate(req.kind, req.part, req.level, req.current, req.target_grade,
                         conds or None, req.pity_used, req.miracle)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    q = r.option_prob
    result = {
        "target_label": label,
        "stages": [{**s.__dict__, "grade_name": pt.GRADE_NAMES[s.grade]} for s in r.stages],
        "grade_up_expected_meso": r.grade_up_expected_meso,
        "option_prob": q,
        "option_expected_attempts": r.option_expected_attempts,
        "option_expected_meso": r.option_expected_meso,
        "attempts_for_confidence": {f"p{int(c*100)}": pt.attempts_for_confidence(q, c) for c in (0.5, 0.9)} if q else None,
        "cost_per_attempt": pt.cost_per_attempt(req.kind, req.level, req.target_grade),
        "expected_total_meso": r.expected_total_meso,
        "percentiles": r.percentiles,
        "histogram": r.histogram,
        "warnings": ["메소 재설정 비용은 2024년 공지 기준이며 인게임 미검증입니다."]
        + (["미라클 타임: 등급 상승 확률 2배만 반영 (천장 처리 미확인)"] if req.miracle else []),
    }
    return result, r.samples, r.expected_total_meso


@router.post("/potential")
def potential(req: PotentialReq):
    return run_potential(req)[0]


@router.get("/potential/presets")
def potential_presets(job: str, part: str, kind: Literal["potential", "additional"], level: int):
    return [{"id": p["id"], "label": p["label"], "conditions": [c.__dict__ for c in p["conditions"]]}
            for p in pt.presets(job, part, kind, level)]


# ------------------------------------------------------------------ 추옵


class FlameCoef(BaseModel):
    main: float = 1
    sub: float = 0.1
    att: float = 4
    all_pct: float = 10


class FlameReq(BaseModel):
    item_type: Literal["armor", "weapon"] = "armor"
    level: int
    boss: bool = True
    method: Literal["meso_reset", "black", "burning", "abyss"] = "meso_reset"
    item_price: float | None = None  # 불꽃 1개 메소 환산가 (메소 재설정 외)
    job: str = "adele"
    coef: FlameCoef = FlameCoef()
    threshold: float | None = None                 # armor: 목표 급수
    requirements: dict[str, int] = {}              # weapon: {옵션: 최소 단계}


def run_flame(req: FlameReq, trials: int = 200_000) -> tuple[dict, np.ndarray, float]:
    job = pt.load_jobs()["jobs"][req.job]
    try:
        cost = fl.cost_per_attempt(req.method, req.item_price)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    curve = None
    if req.item_type == "armor":
        if req.threshold is None:
            raise HTTPException(400, "목표 급수를 입력하세요")
        dist = fl.score_distribution(req.level, req.boss, req.method, job["main_stat"], job["sub_stat"],
                                     job["attack"], fl.ScoreCoef(**req.coef.model_dump()))
        q = fl.prob_score_at_least(dist, req.threshold)
        # 급수 ≥ x 확률 곡선 (차트용, 10급 단위)
        top = max(dist) if dist else 0
        curve = [{"score": x, "prob": fl.prob_score_at_least(dist, x)} for x in range(0, int(top) + 10, 10)]
    else:
        if not req.requirements:
            raise HTTPException(400, "무기 추옵 조건을 입력하세요")
        q = fl.weapon_probability(req.boss, req.method, req.requirements)
    if q <= 0:
        raise HTTPException(400, "목표가 이 수단/장비에서 나올 수 없습니다")
    samples = np.random.default_rng().geometric(q, trials) * cost
    result = {
        "prob": q,
        "expected_attempts": 1 / q,
        "cost_per_attempt": cost,
        "expected_meso": cost / q,
        "attempts_for_confidence": {f"p{int(c*100)}": math.ceil(math.log(1 - c) / math.log(1 - q)) if q < 1 else 1
                                    for c in (0.5, 0.9)},
        "percentiles": {f"p{p}": float(v) for p, v in zip(cmp.PCTS, np.percentile(samples, cmp.PCTS))},
        "curve": curve,
        "warnings": [] if req.boss or req.item_type == "armor" else ["일반(비보스) 무기 공/마 추옵 수치는 GMS 자료 기준입니다."],
    }
    return result, samples, cost / q


@router.post("/flame")
def flame(req: FlameReq):
    return run_flame(req)[0]


# ------------------------------------------------------------------ 종합 (손익분기)


class PlanReq(BaseModel):
    base_price: float = 0           # 베이스(노작/중간단계) 구매가
    base_other_world: bool = False
    market_price: float | None = None  # 완제품 시세
    market_other_world: bool = False
    resale_price: float = 0         # 기존 장비 판매 등록가 (구매 경로에서 수수료 차감 후 회수)
    sell_fee: float | None = None   # 없으면 설정(MVP·PC방)으로 결정
    starforce: StarforceReq | None = None
    potential: PotentialReq | None = None
    additional: PotentialReq | None = None
    flame: FlameReq | None = None


@router.post("/craft/plan")
def craft_plan(req: PlanReq):
    stages: list[cmp.StageCost] = []
    details: dict = {}
    if req.starforce:
        res, samples, e = run_starforce(req.starforce)
        stages.append(cmp.StageCost("스타포스", e, samples))
        details["starforce"] = res
    if req.potential:
        res, samples, e = run_potential(req.potential.model_copy(update={"kind": "potential"}))
        stages.append(cmp.StageCost("잠재능력", e, samples))
        details["potential"] = res
    if req.additional:
        res, samples, e = run_potential(req.additional.model_copy(update={"kind": "additional"}))
        stages.append(cmp.StageCost("에디셔널", e, samples))
        details["additional"] = res
    if req.flame:
        res, samples, e = run_flame(req.flame)
        stages.append(cmp.StageCost("추가옵션", e, samples))
        details["flame"] = res
    if not stages:
        raise HTTPException(400, "직작 단계를 하나 이상 선택하세요")

    base = cmp.effective_buy_price(req.base_price, req.base_other_world)
    market = cmp.effective_buy_price(req.market_price, req.market_other_world) if req.market_price else None
    fee = req.sell_fee if req.sell_fee is not None else _sell_fee()
    result = cmp.compare(stages, base, market, resale_net=req.resale_price * (1 - fee))
    return {"compare": result.__dict__, "details": details, "sell_fee": fee}


def _sell_fee() -> float:
    s = store.load_settings()
    return cmp.sell_fee_rate(s["mvp"], s["pc_room"])
