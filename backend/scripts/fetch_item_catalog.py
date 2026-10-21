"""maplestory.io(KMS 클라이언트 데이터)에서 다음 단계 장비 카탈로그를 받아 JSON으로 저장.

- 방어구·무기: upgrade_paths.yaml 의 단계 이름(앱솔랩스·아케인셰이드·에테르넬, 루타비스 세트명)으로 검색
- 장신구: upgrade_paths.yaml 에 적힌 고정 이름
저장 항목: 이름 → {id, level, sub(장비 분류), jobs(착용 직업 계열)}. id 는 아이콘 조회에도 쓴다.
패치 후 1회 수동 실행하는 용도.

    uv run python scripts/fetch_item_catalog.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.paths import GAME_DATA_DIR  # noqa: E402

VERSION = "389"
URL = f"https://maplestory.io/api/KMS/{VERSION}/item"
SET_TERMS = ["앱솔랩스", "아케인셰이드", "에테르넬", "하이네스", "이글아이", "트릭스터",
             "라이온하트", "드래곤테일", "팔콘윙즈", "레이븐혼", "샤크투스"]  # 뒤 5개: 루타비스 무기
DELAY_SEC = 0.5


def search(term: str) -> list[dict]:
    q = urllib.parse.urlencode({"searchFor": term, "count": 500})
    req = urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "Mozilla/5.0 (MapleGearSim)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main() -> None:
    with open(GAME_DATA_DIR / "upgrade_paths.yaml", encoding="utf-8") as f:
        paths = yaml.safe_load(f)
    fixed = [e["name"] for es in paths["parts"].values() for e in es if e.get("name")]
    items: dict[str, dict] = {}
    for term in SET_TERMS + fixed:
        for x in search(term):
            name, info = x.get("name") or "", x.get("typeInfo") or {}
            if x.get("isCash") or (x.get("requiredLevel") or 0) < 100 or info.get("overallCategory") != "Equip":
                continue
            if not (name.startswith(term) if term in SET_TERMS else name == term) or name in items:
                continue
            items[name] = {"id": x["id"], "level": x["requiredLevel"], "sub": info.get("subCategory"),
                           "jobs": x.get("requiredJobs") or []}
        time.sleep(DELAY_SEC)
    missing = [n for n in fixed if n not in items]
    out = {"source": f"maplestory.io KMS {VERSION}", "fetched_at": date.today().isoformat(), "items": items}
    with open(GAME_DATA_DIR / "item_catalog.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"{len(items)}개 저장" + (f", 못 찾음: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
