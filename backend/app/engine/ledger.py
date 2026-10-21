"""강화 가계부: 스타포스·잠재 재설정·큐브 사용 기록 → 쓴 메소, 기대값 대비 운.

비용
- 스타포스: 1회 비용 = 기본 비용 × (MVP·PC방 할인, 설정값 가정) × (이벤트 할인, 기록값) + 파괴방지 추가 비용
  (슈페리얼 장비, 장비 레벨 미상은 비용 제외)
- 잠재/에디 메소 재설정: 장비 레벨·시도 전 등급의 1회 비용 (potential.yaml)
- 큐브(캐시·이벤트 큐브): 설정한 개당 가치 (기본 0)

운
- 스타포스: 실제 성공·파괴 횟수 vs 기대값 (시도마다 성공·파괴 확률 합, 이벤트 반영)
- 잠재 등급 상승: 메소 재설정·블랙 큐브만 (확률표 보유분). 천장 도달 시도는 확률 1
- 백분위는 포아송-이항 분포로 계산 (P(X ≥ 실제))
- 스타포스 기대 비용 비교: 같은 장비를 이어서 강화한 구간(세션)마다 시작 성 → 끝 성 기대 메소 vs 실제 메소
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from app.engine import potential as pt
from app.engine import starforce as sf

GRADE_MAP = {"레어": "rare", "에픽": "epic", "유니크": "unique", "레전드리": "legendary"}
# 큐브 종류 → 등급 상승 확률표 (확인된 것만)
CUBE_TABLE = {"블랙 큐브": "potential"}


def _num(text) -> float | None:
    if text is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(text))
    return float(m.group()) if m else None


def _applied(text: str | None) -> bool:
    """'파괴 방지 적용' / '이벤트 적용되지 않음' 같은 문구 판정."""
    t = text or ""
    return bool(t) and "미적용" not in t and "않음" not in t and "미해당" not in t and "적용" in t


def _day(row: dict) -> str:
    return (row.get("date_create") or "")[:10]


# ---------------------------------------------------------------- 포아송-이항


def tail_at_least(ps: list[float], k: int) -> float:
    """독립 시행 성공 확률 ps 에서 P(X ≥ k)."""
    if k <= 0:
        return 1.0
    ps = [p for p in ps if p > 0]
    if k > len(ps):
        return 0.0
    if len(ps) > 3000:  # 정규 근사 (연속성 보정)
        arr = np.array(ps)
        mu, var = arr.sum(), (arr * (1 - arr)).sum()
        if var <= 0:
            return float(mu >= k)
        from math import erf, sqrt
        z = (k - 0.5 - mu) / sqrt(var)
        return float(0.5 * (1 - erf(z / sqrt(2))))
    dist = np.zeros(len(ps) + 1)
    dist[0] = 1.0
    for i, p in enumerate(ps, 1):
        dist[1:i + 1] = dist[1:i + 1] * (1 - p) + dist[0:i] * p
        dist[0] *= 1 - p
    return float(min(1.0, max(0.0, dist[k:].sum())))


@dataclass
class Luck:
    attempts: int = 0
    actual: int = 0
    expected: float = 0.0
    ps: list[float] = field(default_factory=list, repr=False)

    def add(self, p: float, hit: bool) -> None:
        self.attempts += 1
        self.actual += int(hit)
        self.expected += p
        self.ps.append(p)

    def to_dict(self) -> dict:
        if not self.attempts:
            return {"attempts": 0, "actual": 0, "expected": 0.0, "below": None}
        a, b = tail_at_least(self.ps, self.actual), tail_at_least(self.ps, self.actual + 1)
        # mid-p: P(X < 실제) + ½·P(X = 실제). 0.5 보다 크면 기대보다 많이 나온 것
        return {"attempts": self.attempts, "actual": self.actual, "expected": self.expected,
                "below": (1 - a) + 0.5 * (a - b)}


# ---------------------------------------------------------------- 스타포스


@dataclass
class SfSettings:
    mvp: str = "none"
    pc_room: bool = False
    mvp_max_star: int = 16


@dataclass
class SfEvent:
    discount: float = 0.0      # 0.3 = 30% 할인
    destroy_cut: float = 0.0   # 0.3 = 파괴 확률 30% 감소
    guaranteed: bool = False


def sf_event(row: dict) -> SfEvent:
    """starforce_event_list 중 이번 시도 성급에 해당하는 이벤트 합성."""
    ev = SfEvent()
    star = row.get("before_starforce_count") or 0
    for e in row.get("starforce_event_list") or []:
        rng = [int(x) for x in re.findall(r"\d+", str(e.get("starforce_event_range") or ""))]
        if len(rng) >= 2 and not (rng[0] <= star <= rng[1]):
            continue
        if len(rng) == 1 and star != rng[0]:
            continue
        ev.discount = max(ev.discount, (_num(e.get("cost_discount_rate")) or 0) / 100)
        ev.destroy_cut = max(ev.destroy_cut, (_num(e.get("destroy_decrease_rate")) or 0) / 100)
        if (_num(e.get("success_rate")) or 0) >= 100:
            ev.guaranteed = True
    return ev


def sf_result(row: dict) -> str:
    r = row.get("item_upgrade_result") or ""
    return "destroy" if "파괴" in r else "success" if "성공" in r else "fail"


def sf_attempt_cost(row: dict, level: int, st: SfSettings, table: dict | None = None) -> float:
    table = table or sf.load_table()
    star = int(row.get("before_starforce_count") or 0)
    bc = sf.base_cost(level, star, table)
    d = table["discount"]
    rate = d["mvp_rate"].get(st.mvp, 0) + (d["pc_room_rate"] if st.pc_room else 0) if star <= st.mvp_max_star else 0.0
    cost = bc * (1 - rate) * (1 - sf_event(row).discount)
    if _applied(row.get("destroy_defence")):
        cost += bc * table["safeguard"]["extra_cost_ratio"]
    return cost


def sf_probs(row: dict, table: dict | None = None) -> tuple[float, float]:
    table = table or sf.load_table()
    star = int(row.get("before_starforce_count") or 0)
    succ, dest = sf.actual_probs(star, table)
    ev = sf_event(row)
    if ev.guaranteed:
        return 1.0, 0.0
    dest *= 1 - ev.destroy_cut
    if _applied(row.get("destroy_defence")):
        dest = 0.0
    return succ, dest


def sf_sessions(rows: list[dict]) -> list[list[dict]]:
    """같은 캐릭터·장비를 성급이 이어지게 강화한 구간으로 나눈다 (rows 는 시간순)."""
    open_: dict[tuple, list[dict]] = {}
    out: list[list[dict]] = []
    for r in rows:
        key = (r.get("character_name"), r.get("target_item"))
        cur = open_.get(key)
        if cur:
            prev = cur[-1]
            if sf_result(prev) != "destroy" and prev.get("after_starforce_count") != r.get("before_starforce_count"):
                out.append(cur)
                cur = None
        if not cur:
            cur = open_[key] = []
        cur.append(r)
    out += [s for s in open_.values() if s]
    out.sort(key=lambda s: s[0].get("date_create") or "")
    return out


def sf_session_expected(sess: list[dict], level: int, st: SfSettings) -> float | None:
    start = int(sess[0].get("before_starforce_count") or 0)
    end = int(sess[-1].get("after_starforce_count") or 0)
    if end <= start or level <= 0:
        return None
    ev = sf_event(sess[0])
    events = sf.Events(discount30=ev.discount >= 0.3, destroy_reduction=ev.destroy_cut > 0)
    try:
        exp, _ = sf.expected(sf.StarforceInput(level=level, start=start, target=end, mvp=st.mvp, pc_room=st.pc_room,
                                               mvp_max_star=st.mvp_max_star, events=events))
    except ValueError:
        return None
    return exp.meso


# ---------------------------------------------------------------- 집계


@dataclass
class Bucket:
    kind: str
    character: str
    item: str
    attempts: int = 0
    meso: float = 0.0
    successes: int = 0
    destroys: int = 0
    grade_ups: int = 0
    first: str = ""
    last: str = ""
    start_star: int | None = None
    end_star: int | None = None
    cube_types: dict[str, int] = field(default_factory=dict)
    no_cost: int = 0  # 비용 계산 못 한 시도

    def touch(self, row: dict) -> None:
        self.attempts += 1
        t = row.get("date_create") or ""
        self.first = min(self.first or t, t)
        self.last = max(self.last, t)


def _grade_before(after: str | None, success: bool) -> str | None:
    g = GRADE_MAP.get(after or "")
    if g and success:
        i = pt.GRADES.index(g)
        return pt.GRADES[i - 1] if i > 0 else g
    return g


def _miracle(row: dict) -> bool:
    return _applied(row.get("miracle_time_flag"))


def build(history: dict[str, list[dict]], levels: dict[str, int], st: SfSettings,
          cube_prices: dict[str, float] | None = None) -> dict:
    cube_prices = cube_prices or {}
    cfg = pt.load_config()
    table = sf.load_table()
    buckets: dict[tuple, Bucket] = {}
    daily: dict[str, dict[str, float]] = {}
    sf_succ, sf_dest, grade = Luck(), Luck(), Luck()
    unknown_levels: dict[str, int] = {}
    superior = 0

    def bucket(kind: str, row: dict) -> Bucket:
        key = (kind, row.get("character_name") or "", row.get("target_item") or "")
        if key not in buckets:
            buckets[key] = Bucket(kind, key[1], key[2])
        b = buckets[key]
        b.touch(row)
        return b

    def spend(row: dict, kind: str, meso: float) -> None:
        d = daily.setdefault(_day(row), {"starforce": 0.0, "potential": 0.0, "cube": 0.0, "attempts": 0})
        d[kind] += meso
        d["attempts"] += 1

    # 스타포스
    sf_rows = sorted(history.get("starforce", []), key=lambda r: r.get("date_create") or "")
    for r in sf_rows:
        b = bucket("starforce", r)
        res = sf_result(r)
        if b.start_star is None:
            b.start_star = r.get("before_starforce_count")
        b.end_star = r.get("after_starforce_count")
        b.successes += res == "success"
        b.destroys += res == "destroy"
        level = levels.get(r.get("target_item") or "", 0)
        star = int(r.get("before_starforce_count") or 0)
        if "미해당" not in (r.get("superior_item_flag") or "미해당"):
            superior += 1
            b.no_cost += 1
            spend(r, "starforce", 0.0)
            continue
        if not level or star >= len(table["base_success"]):
            unknown_levels[r.get("target_item") or ""] = unknown_levels.get(r.get("target_item") or "", 0) + 1
            b.no_cost += 1
            cost = 0.0
        else:
            cost = sf_attempt_cost(r, level, st, table)
        b.meso += cost
        spend(r, "starforce", cost)
        if star < len(table["base_success"]):
            ps, pd = sf_probs(r, table)
            sf_succ.add(ps, res == "success")
            sf_dest.add(pd, res == "destroy")

    sessions = []
    for sess in sf_sessions(sf_rows):
        name = sess[0].get("target_item") or ""
        level = levels.get(name, 0)
        actual = sum(sf_attempt_cost(r, level, st, table) for r in sess) if level else None
        exp = sf_session_expected(sess, level, st)
        sessions.append({
            "character": sess[0].get("character_name"), "item": name, "level": level or None,
            "start": sess[0].get("before_starforce_count"), "end": sess[-1].get("after_starforce_count"),
            "attempts": len(sess), "destroys": sum(sf_result(r) == "destroy" for r in sess),
            "first": sess[0].get("date_create"), "last": sess[-1].get("date_create"),
            "actual": actual, "expected": exp,
        })

    # 잠재·에디 메소 재설정 + 큐브
    for kind in ("potential", "cube"):
        for r in history.get(kind, []):
            b = bucket(kind, r)
            typ = r.get("potential_type") if kind == "potential" else r.get("cube_type")
            typ = typ or ""
            pkind = "additional" if "에디셔널" in typ else "potential"
            after = r.get("additional_potential_option_grade" if pkind == "additional" else "potential_option_grade")
            success = "성공" in (r.get("item_upgrade_result") or "")
            before = _grade_before(after, success)
            b.grade_ups += success
            level = int(r.get("item_level") or 0)
            if kind == "potential":
                cost = pt.cost_per_attempt(pkind, level, before) if before else 0.0
                table_kind = pkind
            else:
                b.cube_types[typ] = b.cube_types.get(typ, 0) + 1
                cost = float(cube_prices.get(typ, 0) or 0)
                table_kind = next((v for k, v in CUBE_TABLE.items() if k in typ and "에디셔널" not in typ), None)
            b.meso += cost
            spend(r, kind, cost)
            if table_kind and before and before != "legendary":
                p = 1.0 if r.get("upgrade_guarantee") else cfg["methods"][table_kind]["grade_up"][before]
                if _miracle(r) and p < 1:
                    p = min(1.0, p * cfg["miracle_time_multiplier"])
                grade.add(p, success)

    cube_counts: dict[str, int] = {}
    for r in history.get("cube", []):
        cube_counts[r.get("cube_type") or "?"] = cube_counts.get(r.get("cube_type") or "?", 0) + 1

    items = sorted(buckets.values(), key=lambda b: -b.meso)
    totals = {k: sum(b.meso for b in items if b.kind == k) for k in ("starforce", "potential", "cube")}
    with_exp = [s for s in sessions if s["expected"] is not None and s["actual"] is not None]
    return {
        "totals": {**totals, "all": sum(totals.values()),
                   "attempts": {k: sum(b.attempts for b in items if b.kind == k) for k in ("starforce", "potential", "cube")}},
        "daily": [{"date": d, **v} for d, v in sorted(daily.items())],
        "items": [b.__dict__ for b in items],
        "characters": sorted({b.character for b in items}),
        "luck": {
            "starforce_success": sf_succ.to_dict(),
            "starforce_destroy": sf_dest.to_dict(),
            "grade_up": grade.to_dict(),
            "starforce_cost": {
                "sessions": len(with_exp),
                "actual": sum(s["actual"] for s in with_exp),
                "expected": sum(s["expected"] for s in with_exp),
            },
        },
        "sessions": sessions,
        "cube_counts": cube_counts,
        "unknown_levels": unknown_levels,
        "superior": superior,
    }
