"""확률형 BM 기댓값 · MVP 작 비교 API."""

from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import store
from app.engine import bm
from app.engine import bm_source
from app.engine import compare as cmp
from app.engine import market as mk
from app.engine import mvp as mv

router = APIRouter(prefix="/api")
EOK = 1e8


@router.get("/bm/products")
def products():
    # 이벤트성 상품 확률표·캐시샵 공지는 30일마다 갱신 (탭을 열 때만 확인, 백그라운드로 받고 끝나면 다음 조회에 반영)
    st = bm_source.status()
    started = st["stale"] and bm_source.refresh_in_background()
    t = bm.load_tables()
    return {**t, "status": {**bm_source.status(), "started": bool(started)}}


@router.get("/bm/market")
def market(product: str, table: int = 0):
    """시세 기록 탭에 같은 이름으로 기록한 매물이 있으면 중앙값 (억)"""
    try:
        _, tb = bm.find_table(product, table)
    except (KeyError, IndexError) as e:
        raise HTTPException(404, "상품 없음") from e
    rows = store.list_listings()
    out = {}
    for r in tb["rows"]:
        est = mk.estimate(mk.match(rows, r["item"]))
        if est:
            out[r["item"]] = {"eok": est.price / EOK, "n": est.n}
    return out


class Bundle(BaseModel):
    count: int = Field(gt=0)
    price: float = Field(gt=0)


class EvalReq(BaseModel):
    product: str
    table: int = 0
    unit_price_won: float = Field(gt=0)
    bundle: Bundle | None = None  # 묶음으로 살 때: 묶음 단위로만 산다 (1회 가격 = 묶음가 ÷ 개수)
    spend_won: float = Field(ge=0)
    values_eok: dict[str, float] = {}
    jackpots: list[str] = []
    won_per_eok: float | None = None
    mvp: str | None = None  # 판매 수수료 계산용 (없으면 설정값)


def _fee(settings: dict, mvp: str | None) -> float:
    return cmp.sell_fee_rate(mvp or settings["mvp"], settings["pc_room"])


def _evaluate(req: EvalReq, settings: dict) -> bm.Result:
    wpe = req.won_per_eok or settings["won_per_eok"]
    if not wpe:
        raise HTTPException(400, "1억 메소당 원 시세를 먼저 정해 주세요")
    try:
        _, tb = bm.find_table(req.product, req.table)
    except (KeyError, IndexError) as e:
        raise HTTPException(404, "상품 없음") from e
    unit, spend = req.unit_price_won, req.spend_won
    if req.bundle:
        unit = req.bundle.price / req.bundle.count
        spend = (spend // req.bundle.price) * req.bundle.price  # 남는 돈으로는 묶음을 못 산다
        if spend <= 0:
            raise HTTPException(400, f"현질 금액이 묶음 1개 가격({req.bundle.price:,.0f}원)보다 적습니다")
    try:
        return bm.evaluate(tb["rows"], {k: v * EOK for k, v in req.values_eok.items()}, set(req.jackpots),
                           unit, spend + 1e-6, wpe, _fee(settings, req.mvp))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/bm/evaluate")
def evaluate(req: EvalReq):
    settings = store.load_settings()
    res = _evaluate(req, settings)
    return {**res.to_dict(), "fee": _fee(settings, req.mvp), "won_per_eok": req.won_per_eok or settings["won_per_eok"]}


@router.get("/mvp/grades")
def grades():
    return mv.load_grades()


class MvpReq(BaseModel):
    current_cash: float = Field(ge=0)
    target: str
    sf_meso_eok: float = 0       # 13주 동안 1~17성 스타포스에 쓸 메소 (억)
    sell_meso_eok: float = 0     # 13주 동안 경매장 판매액 (억)
    other_won: float = 0         # 쿠폰 등 기타 혜택 가치 (원)
    mesomarket_recovery: float = 1.0
    bm: list[EvalReq] = []       # 비교할 확률형 상품 (spend_won 은 모자란 금액으로 덮어씀)


@router.post("/mvp/compare")
def mvp_compare(req: MvpReq):
    settings = store.load_settings()
    wpe = settings["won_per_eok"]
    if not wpe:
        raise HTTPException(400, "1억 메소당 원 시세를 먼저 정해 주세요")
    if req.target not in {g["id"] for g in mv.load_grades()["grades"]}:
        raise HTTPException(400, "알 수 없는 등급")
    need = max(0.0, next(g["cash"] for g in mv.load_grades()["grades"] if g["id"] == req.target) - req.current_cash)
    opts = [mv.Option("메소마켓 (메이플포인트 → 메소)", req.mesomarket_recovery, "mesomarket",
                      "MVP 반영 여부는 게임 내 안내로 확인 ⚠"),
            mv.Option("치장 캐시템 구매 (되팔기 없음)", 0.0, "cash")]
    details = {}
    for b in req.bm:
        step = b.bundle.price if b.bundle else b.unit_price_won
        spend = math.ceil(need / step) * step  # 기준 금액을 넘기려면 1회(묶음) 단위로 올림
        r = _evaluate(b.model_copy(update={"spend_won": spend, "mvp": req.target}), settings)
        p, tb = bm.find_table(b.product, b.table)
        label = p["name"] + (f" · {tb['title']}" if len(p["tables"]) > 1 else "")
        recovery = (r.expected / EOK * wpe) / r.spend_won if r.spend_won else 0.0
        opts.append(mv.Option(label, recovery, "bm", f"{r.pulls}회 · 본전 이상 확률 {r.profit_prob:.0%}", pay=r.spend_won))
        details[label] = {"pulls": r.pulls, "profit_prob": r.profit_prob, "percentiles": r.percentiles}
    out = mv.compare(req.current_cash, req.target, req.sf_meso_eok * EOK, req.sell_meso_eok * EOK, req.other_won, wpe, opts)
    return {**out, "won_per_eok": wpe, "bm_details": details}
