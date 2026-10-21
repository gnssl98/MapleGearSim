"""강화 가계부 API: 본인 계정의 스타포스·잠재 재설정·큐브 사용 기록 집계."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from app import store
from app.engine import ledger as lg
from app.nexon import history as hs
from app.nexon.character import load_items_config
from app.nexon.client import NexonApiError, NexonClient

router = APIRouter(prefix="/api")


def _equipment_levels(client: NexonClient, names: set[str]) -> dict[str, int]:
    """캐릭터 장착 장비(모든 프리셋)에서 장비 이름 → 레벨. 캐시 우선."""
    out: dict[str, int] = {}
    for name in names:
        try:
            q = {"ocid": client.ocid(name)}
            equip = client.get("/maplestory/v1/character/item-equipment", q)
        except NexonApiError:
            continue
        for key in ("item_equipment", "item_equipment_preset_1", "item_equipment_preset_2", "item_equipment_preset_3"):
            for it in equip.get(key) or []:
                lv = int(float((it.get("item_base_option") or {}).get("base_equipment_level") or 0))
                if lv:
                    out[it["item_name"]] = lv
    return out


def resolve_levels(history: dict[str, list[dict]], overrides: dict[str, int],
                   equipment: dict[str, int] | None = None) -> dict[str, int]:
    """장비 레벨: 직접 지정 > 장착 장비 > 잠재·큐브 기록 > 이름 키워드."""
    names = {r.get("target_item") or "" for r in history.get("starforce", [])}
    from_hist = {r["target_item"]: int(r["item_level"]) for k in ("potential", "cube")
                 for r in history.get(k, []) if r.get("target_item") and r.get("item_level")}
    keywords = load_items_config().get("item_level_keywords", {})
    out = {}
    for n in names:
        lv = overrides.get(n) or (equipment or {}).get(n) or from_hist.get(n)
        if not lv:
            lv = next((v for k, v in keywords.items() if k in n), 0)
        if lv:
            out[n] = int(lv)
    return out


@router.get("/ledger")
def ledger(start: date | None = None, end: date | None = None, character: str | None = None):
    today = date.today()
    end = end or today
    start = start or end - timedelta(days=29)
    settings = store.load_settings()
    client = NexonClient()
    try:
        history = hs.fetch(start, end, today=today, client=client)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except NexonApiError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, str(e)) from e
    if character:
        history = {k: [r for r in v if r.get("character_name") == character] for k, v in history.items()}

    cfg = settings["ledger"]
    levels = resolve_levels(history, cfg["item_levels"])
    missing = {r.get("target_item") for r in history["starforce"]} - set(levels)
    if missing:  # 레벨을 못 찾은 장비가 있을 때만 장착 장비 조회 (캐시 우선)
        chars = {r.get("character_name") for r in history["starforce"] if r.get("target_item") in missing}
        levels = resolve_levels(history, cfg["item_levels"], _equipment_levels(client, {c for c in chars if c}))

    st = lg.SfSettings(mvp=settings["mvp"], pc_room=settings["pc_room"], mvp_max_star=settings["mvp_max_star"])
    out = lg.build(history, levels, st, cfg["cube_prices"])
    all_chars = sorted({r.get("character_name") for v in history.values() for r in v if r.get("character_name")})
    return {
        "start": start.isoformat(), "end": min(end, today).isoformat(), "character": character,
        **out,
        "characters": all_chars,
        "levels": levels,
        "assumptions": [
            f"스타포스 MVP·PC방 할인은 현재 설정({settings['mvp']}, PC방 {'O' if settings['pc_room'] else 'X'})으로 가정 "
            "(기록에 할인 정보 없음). 이벤트 할인·파괴 감소·파괴방지는 기록값 반영",
            "스타포스 비용에 파괴 후 복구 비용(스페어·확정 복구 메소)은 포함하지 않음",
            "큐브는 개당 가치를 지정한 종류만 비용에 포함 (기본 0)",
            "등급 상승 운은 메소 재설정·블랙 큐브만 계산 (다른 큐브는 확률표 미보유)",
            "오늘·어제 기록은 매번 새로 조회, 지난 날짜는 캐시 사용 (기록 반영은 최대 5분 지연)",
        ],
    }
