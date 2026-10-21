"""장착 장비 → 같은 부위 다음 단계 장비 후보 (data/game/upgrade_paths.yaml + item_catalog.json)."""

from __future__ import annotations

import json
from functools import lru_cache

import yaml

from app.paths import GAME_DATA_DIR

PART_NAMES = {"hat": "모자", "top": "상의", "bottom": "하의", "overall": "한벌옷", "shoes": "신발", "gloves": "장갑",
              "cape": "망토", "shoulder": "어깨장식", "weapon": "무기", "earring": "귀고리", "face": "얼굴장식",
              "eye": "눈장식", "belt": "벨트", "pendant": "펜던트", "ring": "반지"}
# 카탈로그(maplestory.io) 장비 분류 · 직업 계열 이름
PART_SUB = {"hat": "Hat", "top": "Top", "bottom": "Bottom", "overall": "Overall", "shoes": "Shoes",
            "gloves": "Glove", "cape": "Cape", "shoulder": "Shoulder Accessory"}
CLASS_JOB = {"warrior": "Warrior", "magician": "Magician", "archer": "Bowman", "thief": "Thief", "pirate": "Pirate"}


@lru_cache(maxsize=1)
def load_paths() -> dict:
    with open(GAME_DATA_DIR / "upgrade_paths.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict]:
    p = GAME_DATA_DIR / "item_catalog.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)["items"]


def catalog_id(name: str | None) -> int | None:
    return (load_catalog().get(name or "") or {}).get("id")


def _find(prefixes: list[str], sub: str | None, job: str | None) -> tuple[str, dict] | None:
    for name, x in sorted(load_catalog().items(), key=lambda kv: kv[1]["id"]):
        if any(name.startswith(p) for p in prefixes) and x["sub"] == sub and (not job or job in x["jobs"]):
            return name, x
    return None


def next_steps(item: dict, class_type: str | None) -> list[dict]:
    """같은 부위에서 착용 레벨이 더 높은 장비. 반환: [{tier, name, label, level, part, id}] (낮은 단계부터)"""
    part = item.get("part")
    if part == "ring" and not item.get("potential_grade"):
        return []  # 잠재 없는 반지 = 시드링·특수 반지 (일부러 끼는 것)
    cat = load_catalog()
    mine = cat.get(item["name"]) or {}
    job = CLASS_JOB.get(class_type or "") or (mine.get("jobs") or [None])[0]
    sub = mine.get("sub") if part == "weapon" else PART_SUB.get(part or "")
    out = []
    for e in load_paths()["parts"].get(part) or []:
        prefixes = e["prefix"] if isinstance(e.get("prefix"), list) else [e["prefix"]] if e.get("prefix") else []
        if e["level"] <= (item.get("level") or 0) or any(item["name"].startswith(p) for p in prefixes):
            continue
        if e.get("name"):
            name, x = e["name"], cat.get(e["name"]) or {}
        else:
            found = _find(prefixes, sub, job) if sub else None
            if found is None and part == "weapon":
                continue  # 무기 분류를 모르면 후보 없음
            name, x = found or (None, {})
        if name == item["name"]:
            continue
        level = x.get("level") or e["level"]
        if level <= (item.get("level") or 0):
            continue
        out.append({"tier": e["tier"], "name": name, "label": name or f"{e['tier']} {PART_NAMES.get(part, part)}",
                    "level": level, "part": part, "id": x.get("id")})
    return out
