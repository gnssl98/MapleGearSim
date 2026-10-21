"""시세 추정 / 매물 vs 직작 비교 API (시세 = 기록한 매물)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.api import craft as cr
from app.engine import compare as cmp
from app.engine import market as mk
from app.engine import starforce as sf
from app.engine import tickets as tk
from app.engine.potential import load_jobs
from app.nexon.character import is_boss_flame_item

router = APIRouter(prefix="/api/market")
NO_FLAME = {"ring", "shoulder", "emblem", "secondary", "shield", "force_shield", "heart"}


@router.get("/estimate")
def estimate(item_name: str, star: int | None = None, grade: str | None = None, base: bool = False,
             sell: bool = False):
    """완제품(성 ±1, 같은 잠재 등급) 또는 베이스(노작) 실구매가 중앙값. sell=True 면 등록가 중앙값 (되팔기용)."""
    rows = store.list_listings()
    est = mk.base_price(rows, item_name) if base else \
        mk.estimate(mk.match(rows, item_name, star=star, grade=grade), sell=sell)
    return est.to_dict() if est else None


class CompareReq(BaseModel):
    listing_id: str
    base_price: float | None = None     # 메소. 없으면 기록된 베이스 매물 시세
    base_other_world: bool = False
    resale_price: float = 0             # 이 매물을 사면 팔 기존 장비 등록가 (메소)


@router.post("/craft-compare")
def craft_compare(req: CompareReq):
    """기록된 매물과 같은 스펙을 베이스(노작)부터 직작할 때의 기댓값·손익분기·손해 확률."""
    settings = store.load_settings()
    rows = store.list_listings()
    row = next((r for r in rows if r["id"] == req.listing_id), None)
    if not row:
        raise HTTPException(404, "매물을 찾을 수 없습니다")
    part, level = row.get("slot"), int(mk._f(row.get("item_level")) or 0)
    if not part or not level:
        raise HTTPException(400, "이 매물에 부위와 레벨이 기록되어 있어야 직작 비교를 할 수 있습니다")
    job_id = settings["job"]
    job = load_jobs()["jobs"][job_id]
    warnings: list[str] = []

    base_est = None
    if req.base_price is not None:
        base = cmp.effective_buy_price(req.base_price, req.base_other_world)
        base_src = "직접 입력"
    else:
        base_est = mk.base_price(rows, row["item_name"], exclude_id=row["id"])
        base = base_est.price if base_est else 0.0
        base_src = f"기록된 노작 매물 {base_est.n}건 중앙값" if base_est else "노작 매물 기록 없음 (0으로 계산)"
        if not base_est:
            warnings.append("같은 아이템의 노작(성 0, 잠재 없음/레어) 매물을 기록하면 베이스 가격이 자동 반영됩니다.")

    ev = {k: v for k, v in settings["events"].items() if k != "miracle"}
    star = int(mk._f(row.get("star")) or 0)
    # base 는 이미 실구매가(타서버 수수료 반영)
    plan = cr.PlanReq(base_price=base, market_price=mk.eff_price(row), resale_price=req.resale_price)
    target: dict = {"star": star}
    tix = tk.Tickets(**settings["tickets"])
    s0 = tix.star_start(level, 0, min(star, sf.max_star_for_level(level))) if star > 0 else 0
    if s0:
        warnings.append(tk.note("star17"))
    if star > 0 and s0 < min(star, sf.max_star_for_level(level)):
        plan.starforce = cr.StarforceReq(
            level=level, start=s0, target=min(star, sf.max_star_for_level(level)), mvp=settings["mvp"],
            pc_room=settings["pc_room"], mvp_max_star=settings["mvp_max_star"], events=cr.EventsModel(**ev),
            spare_price=base, optimize=True, trials=50_000)  # 파괴 시 스페어 = 같은 베이스, 파방·복구 최적 정책
    for kind, prefix, grade_key in (("potential", "pot", "potential_grade"), ("additional", "add", "additional_grade")):
        lines = mk.listing_lines(row, prefix)
        grade = row.get(grade_key) or ("legendary" if lines else "")
        conds = mk.conditions_from_lines(lines, job)
        if not grade or grade == "rare" and not conds:
            continue
        g0 = tix.grade_start(kind, "rare")
        if tk.GRADES.index(g0) > tk.GRADES.index(grade):
            g0 = "rare"  # 매물보다 높은 등급을 주는 주문서는 이 비교에 쓰지 않음
        elif g0 != "rare":
            warnings.append(tk.note(kind))
        req_model = cr.PotentialReq(kind=kind, part=part, level=level, current=g0, target_grade=grade, job=job_id,
                                    conditions=[cr.ConditionModel(**c.__dict__) for c in conds],
                                    miracle=settings["events"].get("miracle", False))
        setattr(plan, kind, req_model)
        target[kind] = {"grade": grade, "conditions": [c.__dict__ for c in conds]}
    fs = mk._f(row.get("flame_score"))
    if fs and part not in NO_FLAME and part != "weapon":
        plan.flame = cr.FlameReq(item_type="armor", level=level, boss=is_boss_flame_item(row["item_name"]),
                                 method=settings["flame_method"], job=job_id, coef=cr.FlameCoef(**settings["flame_coef"]),
                                 threshold=fs)
        target["flame_score"] = fs
    elif part == "weapon":
        warnings.append("무기 추옵은 매물에 n추가 기록되지 않아 비교에서 제외했습니다.")

    try:
        res = cr.craft_plan(plan)
    except HTTPException as e:
        raise HTTPException(e.status_code, f"직작 비교 불가: {e.detail}") from e
    warnings += [w for d in res["details"].values() for w in d.get("warnings", [])]
    return {**res, "listing": row, "target": target, "base_source": base_src,
            "base_estimate": base_est.to_dict() if base_est else None, "warnings": warnings}
