"""로컬 사용자 데이터: 설정(JSON), 시세 매물(CSV 누적)."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path

from app.paths import USER_DATA_DIR

SETTINGS_PATH = USER_DATA_DIR / "settings.json"
LISTINGS_PATH = USER_DATA_DIR / "listings.csv"

DEFAULT_SETTINGS = {
    "job": "adele",
    "characters": [],  # 즐겨찾는 캐릭터 이름
    "mvp": "none",
    "pc_room": False,
    "mvp_max_star": 16,
    "won_per_eok": None,  # 메소마켓 1억 메소당 MP(≈원)
    "events": {
        "discount30": False,
        "destroy_reduction": False,
        "guaranteed_5_10_15": False,
        "plus_one": False,
        "recovery_discount": False,
        "miracle": False,
    },
    "flame_coef": {"main": 1, "sub": 0.1, "att": 4, "all_pct": 10},
    # 환산 가정 (engine/hwansan.py Assumptions)
    "hwansan": {
        "boss_armor": 300,
        "crit_rate_100": True,
        "extra_main_pct": 0,
        "extra_att_pct": 0,
        "extra_main_static": 0,
    },
    "budget_eok": 50,
    "excluded_items": [],
    # 캐릭터별 보스용/재획용 프리셋 번호 {이름: {"boss": {"equipment": 1, "ability": 1, "hyper": 1}, "farming": {...}}}
    # 없으면 자동 추정 (nexon/presets.py guess)
    "presets": {},  # 추천에서 뺄 장비 이름 (강화 불가 이벤트 장비 등)
    "flame_method": "meso_reset",
    # 강화 가계부: 큐브 종류별 개당 가치(메소), 기록에 레벨이 없는 장비의 레벨 직접 지정
    "ledger": {"cube_prices": {}, "item_levels": {}},
    # 보유한 이벤트 보상 아이템 개수 (engine/tickets.py). star17_max_level: 17성 강화권 사용 가능 최대 장비 레벨 ⚠
    "tickets": {"unique_potential": 0, "epic_additional": 0, "star17": 0, "star17_max_level": 200},
    # 확률형 BM 탭: 상품별 1회 가격(원), 아이템별 경매장 가격(억), 상품·표별 당첨 아이템
    # options: 상품별 고른 구매 방법 번호 (-1 = 직접 입력 가격)
    "bm": {"unit_prices": {}, "values": {}, "jackpots": {}, "options": {}},
    # MVP 작 탭 입력
    "mvp_plan": {"current_cash": 0, "target": "silver", "sf_meso_eok": 0, "sell_meso_eok": 0, "other_won": 0,
                 "mesomarket_recovery": 1.0, "bm": []},
}

LISTING_FIELDS = [
    "id", "observed_at", "item_name", "slot", "item_level", "star",
    "potential_grade", "pot1", "pot2", "pot3",
    "additional_grade", "add1", "add2", "add3",
    "flame_score", "flame_detail", "cuttable_count",
    "price_meso", "world_type", "note", "deleted",
]


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        return _merge(DEFAULT_SETTINGS, json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(data: dict) -> dict:
    merged = _merge(DEFAULT_SETTINGS, data)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def _read_rows(path: Path | None = None) -> list[dict]:
    path = path or LISTINGS_PATH
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_rows(rows: list[dict], path: Path | None = None) -> None:
    path = path or LISTINGS_PATH
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:  # BOM: 엑셀 한글 호환
        w = csv.DictWriter(f, fieldnames=LISTING_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LISTING_FIELDS})
    tmp.replace(path)


def list_listings(include_deleted: bool = False) -> list[dict]:
    rows = _read_rows()
    return rows if include_deleted else [r for r in rows if r.get("deleted") not in ("1", "true", "True")]


def add_listing(data: dict) -> dict:
    row = {k: data.get(k, "") for k in LISTING_FIELDS}
    row["id"] = uuid.uuid4().hex[:12]
    row["observed_at"] = data.get("observed_at") or datetime.now().isoformat(timespec="minutes")
    row["deleted"] = "0"
    exists = LISTINGS_PATH.exists()
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LISTINGS_PATH, "a", encoding="utf-8-sig" if not exists else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LISTING_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)
    return row


def delete_listing(listing_id: str) -> bool:
    """삭제는 행을 지우지 않고 deleted=1 플래그만 세운다 (이력 보존)."""
    rows = _read_rows()
    found = False
    for r in rows:
        if r["id"] == listing_id:
            r["deleted"] = "1"
            found = True
    if found:
        _write_rows(rows)
    return found
