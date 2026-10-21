"""캐릭터 연동 API (넥슨 오픈 API) + 환산·업그레이드 추천."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.engine import compare as cmp
from app.engine import flame as fl
from app.engine import hwansan as hw
from app.engine import recommend as rc
from app.engine import shopping as sh
from app.engine import starforce as sf
from app.engine import tickets as tk
from app.engine.potential import load_jobs
from app.nexon.character import load_character
from app.nexon.client import NexonApiError, clear_cache, load_api_key

router = APIRouter(prefix="/api")


VIEWS = ("current", "boss", "farming")


def _load(name: str, refresh: bool = False, view: str = "boss") -> tuple[dict, dict]:
    if view not in VIEWS:
        raise HTTPException(400, f"view 는 {VIEWS} 중 하나")
    settings = store.load_settings()
    try:
        data = load_character(name, refresh=refresh, coef=fl.ScoreCoef(**settings["flame_coef"]),
                              assumptions=hw.Assumptions(**settings["hwansan"]), view=view,
                              choice=settings["presets"].get(name))
    except NexonApiError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, str(e)) from e
    return data, settings


@router.get("/character/status")
def status():
    return {"has_key": bool(load_api_key())}


@router.get("/character/{name}")
def character(name: str, refresh: bool = False, view: str = "boss"):
    return _load(name, refresh, view)[0]


@router.delete("/character/cache")
def delete_cache():
    return {"deleted": clear_cache()}


class RecommendReq(BaseModel):
    name: str
    budget_eok: float | None = None


def _recommend_ctx(name: str):
    """템 추천·쇼핑 리스트 공통: 보스용 프리셋 기준 캐릭터 + 추천 컨텍스트 + 제외 반영 장비."""
    data, settings = _load(name, view="boss")
    if not data["supported"]:
        raise HTTPException(400, f"지원하지 않는 직업입니다: {data['class']}")
    h = data["hwansan"]
    ev = {k: v for k, v in settings["events"].items() if k != "miracle"}
    ctx = rc.Context(
        spec=hw.Spec(**h["spec"]), a=hw.Assumptions(**h["assumptions"]), job_id=data["job_id"],
        job=load_jobs()["jobs"][data["job_id"]], char_level=data["level"], mvp=settings["mvp"],
        pc_room=settings["pc_room"], mvp_max_star=settings["mvp_max_star"], events=sf.Events(**ev),
        coef=fl.ScoreCoef(**settings["flame_coef"]), flame_method=settings["flame_method"],
        sell_fee=cmp.sell_fee_rate(settings["mvp"], settings["pc_room"]),
        tickets=tk.Tickets(**settings["tickets"]),
    )
    excluded = set(settings["excluded_items"])
    items = [it for it in data["items"] if it["name"] not in excluded]
    return data, settings, ctx, items, excluded


@router.post("/recommend")
def recommend(req: RecommendReq):
    data, settings, ctx, items, excluded = _recommend_ctx(req.name)
    h = data["hwansan"]
    cands = rc.generate(ctx, items, store.list_listings())
    budget = (req.budget_eok if req.budget_eok is not None else settings["budget_eok"]) * rc.EOK
    return {
        "name": data["name"],
        "candidates": [c.to_dict() for c in cands],
        "plan": rc.optimize_budget(cands, budget),
        "budget": budget,
        "assumptions": h["assumptions"],
        "spec": h["spec"],
        "basis": h["basis"],
        "table": h["table"],
        "excluded": sorted(excluded),
        "presets": data["presets"],
        "warnings": h.get("warnings", []),
        "notes": [
            "이득 = 환산 주스탯 (최종 주스탯 1 = 1, 현재 스펙 기준 데미지 공식 차분)",
            "같은 장비에 여러 강화를 조합하면 이득을 단순 합산 (근사)",
            "기존 장비 강화 후보의 스타포스 비용에는 파괴 시 스페어 비용이 포함되지 않음 (노작+직작 후보는 노작 시세로 포함)",
            "매물 구매·노작+직작 후보는 기존 장비 되팔기(기록된 비슷한 매물 시세 × (1-수수료))를 비용에서 차감",
        ],
    }


class ShoppingReq(BaseModel):
    name: str
    budget_eok: float | None = None
    threshold: float | None = None  # 억당 환산 기준. 없으면 예산 최적 조합에서 자동


@router.post("/shopping")
def shopping(req: ShoppingReq):
    data, settings, ctx, items, excluded = _recommend_ctx(req.name)
    listings = store.list_listings()
    budget = (req.budget_eok if req.budget_eok is not None else settings["budget_eok"]) * rc.EOK
    auto = None
    if req.threshold is None:
        auto = sh.threshold_from_plan(rc.optimize_budget(rc.generate(ctx, items, listings), budget))
    threshold = req.threshold if req.threshold is not None else auto
    rows = sh.shopping_list(ctx, items, listings, threshold)
    return {
        "name": data["name"],
        "budget": budget,
        "threshold": threshold,
        "threshold_auto": auto,
        "targets": [t.to_dict() for t in rows],
        "presets": data["presets"],
        "excluded": sorted(excluded),
        "warnings": data["hwansan"].get("warnings", []),
    }
