"""넥슨 공식 확률형 아이템 페이지에서 전체 상품 확률표를 받아 하드코딩 스냅숏(data/game/bm_tables.json)으로 저장.

평소에는 이벤트성 상품만 앱이 30일마다 자동으로 받는다(app/engine/bm_source.py).
고정 상품의 확률이 바뀌었거나 새 상품을 스냅숏에 넣고 싶을 때 1회 수동 실행.

    uv run python scripts/fetch_bm_tables.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine import bm_source as src  # noqa: E402
from app.paths import GAME_DATA_DIR  # noqa: E402


def main() -> None:
    products = src.fetch_products()
    out = {"source": src.BASE + "/Guide/CashShop/Probability", "fetched_at": date.today().isoformat(), "products": products}
    with open(GAME_DATA_DIR / "bm_tables.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(products)}개 상품, 표 {sum(len(p['tables']) for p in products)}개 저장")
    new = [p["id"] for p in products if p["id"] not in src.catalog()]
    if new:
        print(f"bm_products.yaml 에 분류가 없는 상품 (event 로 처리): {new}")


if __name__ == "__main__":
    main()
