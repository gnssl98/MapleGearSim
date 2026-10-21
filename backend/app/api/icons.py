"""아이템 아이콘.

- 장착 장비: 넥슨 오픈 API 장비 응답(로컬 캐시)의 item_icon URL 로 리다이렉트
- 그 외(다음 단계 후보 등): item_catalog.json 의 id 로 maplestory.io(KMS 클라이언트 데이터)에서 받아 로컬에 캐시
화면에서는 이름만 알면 /api/icon/by-name?name=... 으로 쓴다.
"""

from __future__ import annotations

import json
import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, Response

from app.engine.next_step import catalog_id
from app.nexon.client import CACHE_DIR
from app.paths import DATA_DIR

router = APIRouter(prefix="/api")
ICON_DIR = DATA_DIR / "cache" / "icons"
URL = "https://maplestory.io/api/KMS/389/item/{id}/icon"
HEADERS = {"Cache-Control": "public, max-age=2592000"}
_equipped: dict[str, str] = {}
_equipped_at = 0.0


def equipped_icons() -> dict[str, str]:
    """캐시된 모든 캐릭터 장비 응답에서 이름 → 넥슨 아이콘 URL (1분마다 다시 읽음)."""
    global _equipped, _equipped_at
    if time.time() - _equipped_at > 60:
        out: dict[str, str] = {}
        for f in CACHE_DIR.glob("maplestory_v1_character_item-equipment_*.json"):
            try:
                body = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            body = body.get("body", body)
            for v in body.values():
                for it in v if isinstance(v, list) else []:
                    if isinstance(it, dict) and it.get("item_name") and it.get("item_icon"):
                        out[it["item_name"]] = it["item_icon"]
        _equipped, _equipped_at = out, time.time()
    return _equipped


@router.get("/icon/by-name")
def icon_by_name(name: str):
    if url := equipped_icons().get(name):
        return RedirectResponse(url, headers=HEADERS)
    if item_id := catalog_id(name):
        return icon(item_id)
    raise HTTPException(404, "아이콘 없음")


@router.get("/icon/{item_id}")
def icon(item_id: int):
    path = ICON_DIR / f"{item_id}.png"
    if not path.exists():
        try:
            r = httpx.get(URL.format(id=item_id), timeout=15, headers={"User-Agent": "Mozilla/5.0 (MapleGearSim)"})
        except httpx.HTTPError as e:
            raise HTTPException(502, f"아이콘을 받을 수 없습니다: {e}") from e
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
            raise HTTPException(404, "아이콘 없음")
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return Response(path.read_bytes(), media_type="image/png", headers=HEADERS)
