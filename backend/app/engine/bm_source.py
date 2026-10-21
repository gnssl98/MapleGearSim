"""확률형 BM 확률표·가격 출처.

- 하드코딩 스냅숏: data/game/bm_tables.json (scripts/fetch_bm_tables.py 로 생성, 저장소에 포함)
- 고정 상품(kind: fixed)은 스냅숏만 쓴다.
- 이벤트성 상품(kind: event, 목록에 없는 새 상품 포함)은 30일마다 공식 확률 페이지에서 다시 받아
  data/cache/bm/tables.json 에 둔다. 받기 전이나 실패하면 스냅숏을 쓴다.
- 가격: data/game/bm_products.yaml 의 구매 방법(묶음)별 가격 (+ 화면 입력). 공식 캐시샵 공지는 가격이 이미지라 숫자는 못 읽고,
  30일마다 공지 목록만 받아서 상품 이름이 들어간 최근 공지를 기록한다 (가격 기준일 이후 공지가 있으면 화면에 알림).
갱신은 사용자가 확률형 BM 탭을 열 때만 확인한다 (백그라운드 주기 호출 없음).
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.request
from datetime import date, datetime
from functools import lru_cache

import yaml

from app.paths import DATA_DIR, GAME_DATA_DIR

BASE = "https://maplestory.nexon.com"
START = "/Guide/CashShop/Probability/RoyalStyle"
NOTICE_LIST = "/News/CashShop/Sale"
CACHE_PATH = DATA_DIR / "cache" / "bm" / "tables.json"
MAX_AGE_DAYS = 30
DELAY_SEC = 0.5

TOKEN_RE = re.compile(r'<h2 class="per_item_h5">(.*?)</h2>|<h3 class="sq_bul">(.*?)</h3>|(<table.*?</table>)', re.S)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)
# 캐시 확률형 상품만: CashShop/Probability, OtherProbability/Game(컬렉션)·Box(알쏭달쏭 상자).
# 소문자 game/* (주문서·추가옵션·소울 등 인게임 확률)은 제외
LINK_RE = re.compile(r'<a href="(/Guide/(?:CashShop/Probability|OtherProbability/(?:Game|Box))/[A-Za-z0-9]+)"[^>]*>(.*?)</a>', re.S)
H2_RE = re.compile(r'<h2 class="per_item_h5">(.*?)</h2>', re.S)
PROB_RE = re.compile(r"([\d.]+)\s*%")
NOTICE_RE = re.compile(r'<a href="(/News/CashShop/Sale/\d+)"[^>]*>(.*?)</a>', re.S)


def _text(x: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def get(path: str) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0 (MapleGearSim)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


# ---------------------------------------------------------------- 확률표 파싱


def parse_table(t: str) -> list[dict]:
    """[{group, item, prob}] — 확률(%) 칸이 있는 행만. rowspan 된 '구분' 칸은 아래 행에 이어 붙인다."""
    rows, group, left = [], "", 0
    for r in ROW_RE.findall(t):
        cells = [(attrs, _text(c)) for attrs, c in CELL_RE.findall(r)]
        if not cells:
            continue
        if left <= 0 and len(cells) >= 3:
            attrs, group = cells[0]
            m = re.search(r'rowspan="(\d+)"', attrs)
            left = int(m.group(1)) if m else 1
            cells = cells[1:]
        elif left <= 0:
            group = ""
        left -= 1
        m = PROB_RE.fullmatch(cells[-1][1]) if cells else None
        if len(cells) < 2 or not m:
            continue  # 옵션 설명 표 등 확률 형식이 아닌 행
        rows.append({"group": group, "item": cells[0][1], "prob": float(m.group(1)) / 100})
    return rows


def parse_page(s: str) -> list[dict]:
    tables, h2, h3 = [], "", ""
    for m in TOKEN_RE.finditer(s):
        if m.group(1) is not None:
            h2, h3 = _text(m.group(1)), ""
        elif m.group(2) is not None:
            h3 = _text(m.group(2)).strip("<> ")
        else:
            rows = parse_table(m.group(3))
            total = sum(r["prob"] for r in rows)
            title = " · ".join(x for x in (h2, h3) if x)
            # 옵션 개수·유지 기간 등 보조 표는 제외 (확률 합이 100%가 아니거나 '옵션' 설명 표)
            if not rows or abs(total - 1) > 0.02 or "옵션" in title:
                continue
            if any(t["title"] == title for t in tables) and rows[0]["group"]:
                title = f"{title} · {rows[0]['group']}"  # 마스터피스처럼 부위별 표가 같은 제목
            tables.append({"title": title, "rows": rows, "total": round(total, 6)})
    if len(tables) > 1 and tables[0]["rows"][0]["group"] and " · " not in tables[0]["title"] \
            and any(t["title"].startswith(tables[0]["title"] + " · ") for t in tables[1:]):
        tables[0]["title"] = f"{tables[0]['title']} · {tables[0]['rows'][0]['group']}"
    return tables


def product_links() -> dict[str, str]:
    links: dict[str, str] = {}
    for path, name in LINK_RE.findall(get(START)):
        links[path] = _text(name)  # 분류 메뉴(치장성·게임 등) 링크가 먼저 나오므로 마지막 이름 = 상품 이름
    return links


def fetch_products(only: set[str] | None = None, skip: set[str] = frozenset()) -> list[dict]:
    """공식 페이지에서 상품별 확률표. only: 이 id 만, skip: 이 id 는 건너뜀"""
    out = []
    for path, name in product_links().items():
        pid = path.rsplit("/", 1)[1]
        if (only is not None and pid not in only) or pid in skip:
            continue
        time.sleep(DELAY_SEC)
        page = get(path)
        tables = parse_page(page)
        h2 = H2_RE.search(page)  # 메뉴 이름이 없을 때만
        if tables:
            out.append({"id": pid, "name": name or (_text(h2.group(1)) if h2 else pid), "url": BASE + path,
                        "tables": tables})
    return out


def fetch_notices() -> list[dict]:
    """캐시샵 판매 공지 목록 [{title, url, date}] (제목 앞 'M월 D일' → 올해/작년 날짜)"""
    out, today = [], date.today()
    seen = set()
    for path, title in NOTICE_RE.findall(get(NOTICE_LIST)):
        t = _text(title)
        if not t or path in seen:
            continue  # 같은 공지의 이미지 링크 등
        seen.add(path)
        m = re.match(r"(\d{1,2})월 (\d{1,2})일", t)
        d = None
        if m:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
            if d > today:
                d = d.replace(year=today.year - 1)
        out.append({"title": t, "url": BASE + path, "date": d.isoformat() if d else None})
    return out


# ---------------------------------------------------------------- 불러오기 · 갱신


@lru_cache(maxsize=1)
def catalog() -> dict:
    with open(GAME_DATA_DIR / "bm_products.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["products"]


def kind_of(pid: str) -> str:
    return (catalog().get(pid) or {}).get("kind", "event")


def snapshot() -> dict:
    p = GAME_DATA_DIR / "bm_tables.json"
    if not p.exists():
        return {"products": [], "fetched_at": None}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def cached() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except ValueError:
        return None


def is_stale(c: dict | None, today: date | None = None) -> bool:
    if not c or not c.get("fetched_at"):
        return True
    return ((today or date.today()) - date.fromisoformat(c["fetched_at"][:10])).days >= MAX_AGE_DAYS


_lock = threading.Lock()
_state = {"refreshing": False, "error": None}


def refresh() -> dict:
    """이벤트성 상품 확률표 + 캐시샵 공지 목록을 받아 캐시에 저장."""
    fixed = {pid for pid, c in catalog().items() if c.get("kind") == "fixed"}
    products = fetch_products(skip=fixed)
    notices = fetch_notices()
    out = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "products": products, "notices": notices}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def refresh_in_background() -> bool:
    """오래됐으면 백그라운드로 갱신 시작. 이미 진행 중이면 False"""
    with _lock:
        if _state["refreshing"]:
            return False
        _state.update(refreshing=True, error=None)

    def run():
        try:
            refresh()
            load.cache_clear()
        except Exception as e:  # noqa: BLE001 — 네트워크 실패 시 스냅숏으로 계속
            _state["error"] = str(e)
        finally:
            _state["refreshing"] = False

    threading.Thread(target=run, daemon=True).start()
    return True


def status() -> dict:
    c = cached()
    return {"refreshing": _state["refreshing"], "error": _state["error"],
            "event_fetched_at": c.get("fetched_at") if c else None, "stale": is_stale(c)}


def notice_key(name: str) -> str:
    """상품 이름 → 공지 제목에서 찾을 말 ('위습의 원더베리' → '원더베리', '루나 크리스탈 스윗' → '루나 크리스탈')"""
    words = re.sub(r"^(스페셜|위습의)\s*", "", name).split()
    return " ".join(words[:2]) if len(words) >= 3 else words[0]


def notice_for(name: str, notices: list[dict]) -> dict | None:
    key, special = notice_key(name), "스페셜" in name
    for n in notices:  # 최신순
        if key in n["title"] and ("스페셜" in n["title"]) == special:
            return n
    return None


@lru_cache(maxsize=1)
def load() -> dict:
    """화면용: 고정 = 스냅숏, 이벤트 = 캐시(없으면 스냅숏). 상품마다 source·기본 가격·최근 공지."""
    snap = snapshot()
    c = cached() or {}
    fresh = {p["id"]: p for p in c.get("products", [])}
    notices = c.get("notices", [])
    out = []
    ids = [p["id"] for p in snap["products"]] + [pid for pid in fresh if pid not in {p["id"] for p in snap["products"]}]
    snap_by = {p["id"]: p for p in snap["products"]}
    for pid in ids:
        kind = kind_of(pid)
        use_fresh = kind == "event" and pid in fresh
        p = dict(fresh[pid] if use_fresh else snap_by[pid])
        meta = catalog().get(pid) or {}
        notice = notice_for(p["name"], notices)
        price_date = str(meta.get("price_date")) if meta.get("price_date") else None
        opts = [{**o, "unit": o["price"] / o["count"]} for o in meta.get("options") or []]
        best = min(range(len(opts)), key=lambda i: (opts[i]["unit"], -opts[i]["count"])) if opts else None
        p.update(kind=kind, source="monthly" if use_fresh else "snapshot",
                 tables_date=c.get("fetched_at", "")[:10] if use_fresh else snap.get("fetched_at"),
                 options=opts, best_option=best, note=meta.get("note"),
                 default_price=opts[best]["unit"] if opts else None,
                 price_date=price_date, price_source=meta.get("price_source"),
                 notice=notice,
                 price_maybe_changed=bool(notice and notice.get("date") and (not price_date or notice["date"] > price_date)))
        out.append(p)
    return {"products": out, "snapshot_at": snap.get("fetched_at"), "event_fetched_at": c.get("fetched_at")}
