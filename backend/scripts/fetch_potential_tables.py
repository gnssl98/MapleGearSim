"""넥슨 공식 큐브 확률 페이지에서 잠재/에디셔널 옵션 확률표를 수집해 JSON으로 저장.

공식 확률 공개 페이지(maplestory.nexon.com/Guide/OtherProbability/cube/*)가 내부적으로
호출하는 검색 엔드포인트를 사용한다. 패치 후 1회 수동 실행하는 용도.

    uv run python scripts/fetch_potential_tables.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.paths import GAME_DATA_DIR  # noqa: E402

URL = "https://maplestory.nexon.com/Guide/OtherProbability/cube/GetSearchProbList"
CUBES = {"potential": (5062010, "black"), "additional": (5062500, "addi")}
GRADES = {3: "unique", 4: "legendary"}
PARTS = {
    1: "weapon", 2: "emblem", 3: "secondary", 4: "force_shield", 5: "shield", 6: "hat", 7: "top",
    8: "overall", 9: "bottom", 10: "shoes", 11: "gloves", 12: "cape", 13: "belt", 14: "shoulder",
    15: "face", 16: "eye", 17: "earring", 18: "ring", 19: "pendant", 20: "heart",
}
LEVELS = [160, 200, 250]
DELAY_SEC = 0.5

TABLE_RE = re.compile(r'<table class="cube_data _(\d)">(.*?)</table>', re.S)
ROW_RE = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>([\d.]+)%</td>\s*</tr>", re.S)


def fetch(cube_id: int, page: str, grade: int, part: int, level: int) -> list[list[dict]]:
    data = urllib.parse.urlencode(
        {"nCubeItemID": cube_id, "nGrade": grade, "nPartsType": part, "nReqLev": level}
    ).encode()
    req = urllib.request.Request(
        URL,
        data=data,
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://maplestory.nexon.com/Guide/OtherProbability/cube/{page}",
            "User-Agent": "Mozilla/5.0 (personal probability table collector)",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
    lines: list[list[dict]] = [[], [], []]
    for idx, inner in TABLE_RE.findall(body):
        for text, prob in ROW_RE.findall(inner):
            lines[int(idx) - 1].append({"option": html.unescape(text).strip(), "prob": float(prob) / 100})
    return lines


def main() -> None:
    out = {"fetched_at": date.today().isoformat(), "source": URL, "tables": {}}
    for kind, (cube_id, page) in CUBES.items():
        for grade, grade_name in GRADES.items():
            for part, part_name in PARTS.items():
                for level in LEVELS:
                    key = f"{kind}/{grade_name}/{part_name}/{level}"
                    lines = fetch(cube_id, page, grade, part, level)
                    if not any(lines):
                        print(f"  (empty) {key}")
                    else:
                        out["tables"][key] = lines
                        print(f"  {key}: {[len(l) for l in lines]}")
                    time.sleep(DELAY_SEC)
    path = GAME_DATA_DIR / "potential_options.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {len(out['tables'])} tables → {path}")


if __name__ == "__main__":
    main()
