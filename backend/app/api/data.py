"""설정 / 시세 매물 / 메타 정보 API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.engine import flame as fl
from app.engine import potential as pt
from app.engine import starforce as sf

router = APIRouter(prefix="/api")

PARTS = [
    ("weapon", "무기"), ("secondary", "보조무기"), ("emblem", "엠블렘"), ("hat", "모자"), ("top", "상의"),
    ("bottom", "하의"), ("overall", "한벌옷"), ("shoes", "신발"), ("gloves", "장갑"), ("cape", "망토"),
    ("shoulder", "어깨장식"), ("belt", "벨트"), ("face", "얼굴장식"), ("eye", "눈장식"), ("earring", "귀고리"),
    ("ring", "반지"), ("pendant", "펜던트"), ("heart", "기계심장"), ("shield", "방패"),
    ("force_shield", "포스실드/소울링"),
]


@router.get("/meta")
def meta():
    jobs = pt.load_jobs()
    return {
        "jobs": [{"id": k, **v} for k, v in jobs["jobs"].items()],
        "parts": [{"id": i, "name": n} for i, n in PARTS],
        "grades": [{"id": g, "name": pt.GRADE_NAMES[g]} for g in pt.GRADES],
        "flame_methods": [{"id": k, "label": v["label"], "meso": "cost_meso" in v}
                          for k, v in fl.load_config()["methods"].items()],
        "starforce": {
            "version": sf.load_table()["version"],
            "max_star_by_level": sf.load_table()["max_star_by_level"],
            "safeguard_stars": sf.load_table()["safeguard"]["stars"],
        },
        "potential_tables_fetched_at": pt.load_option_tables().get("fetched_at"),
    }


@router.get("/settings")
def get_settings():
    return store.load_settings()


@router.put("/settings")
def put_settings(data: dict):
    return store.save_settings(data)


class ListingReq(BaseModel):
    item_name: str
    slot: str = ""
    item_level: int | None = None
    star: int | None = None
    potential_grade: str = ""
    pot1: str = ""
    pot2: str = ""
    pot3: str = ""
    additional_grade: str = ""
    add1: str = ""
    add2: str = ""
    add3: str = ""
    flame_score: float | None = None
    flame_detail: str = ""
    cuttable_count: int | None = None
    price_meso: float
    world_type: str = "own"  # own | other
    note: str = ""
    observed_at: str | None = None


@router.get("/listings")
def get_listings():
    return store.list_listings()


@router.post("/listings")
def post_listing(req: ListingReq):
    data = {k: ("" if v is None else v) for k, v in req.model_dump().items()}
    return store.add_listing(data)


@router.delete("/listings/{listing_id}")
def remove_listing(listing_id: str):
    if not store.delete_listing(listing_id):
        raise HTTPException(404, "매물을 찾을 수 없습니다")
    return {"ok": True}
