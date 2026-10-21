"""구매 상한가 쇼핑 리스트: 경매장 시세 없이 "이 스펙 매물이면 얼마까지 사도 되나"를 계산.

부위마다 현재 장비보다 좋은 목표 스펙(같은 아이템, 목표 성 이상 + 잠재 목표)을 만들고
- 직작 대체 비용: 내 장비를 그 스펙까지 직접 올리는 기대 비용 (스타포스 + 잠재)
- 효율 기준가: 이득(환산) ÷ 기준 억당 환산 (예산 최적 조합의 마지막 선택 효율)
상한가 = min(직작 대체 비용, 효율 기준가) + 기존 장비 되팔기 금액.
매물 가격이 상한가 이하이면 구매가 직작·다른 업그레이드보다 낫다는 뜻이다.
에디·추옵은 현재 장비 이상인 매물을 가정한다 (검색 조건에 포함).

다음 단계 장비(장착하지 않은 상위 템)는 환산 이득을 모르므로(기본 스탯·세트 데이터 없음) 직작 비용만 본다:
상한가 = 노작 구매가 + 노작 0성 → 목표 성 기대 비용 + 레어 → 목표 잠재 기대 비용.
지금 장비는 사든 직작하든 똑같이 팔게 되므로 되팔기는 더하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engine import gear
from app.engine import hwansan as hw
from app.engine import market as mk
from app.engine import next_step as ns
from app.engine import potential as pt
from app.engine import recommend as rc
from app.engine import starforce as sf
from app.engine import tickets as tk
from app.nexon.character import load_items_config

STAR_TARGETS = (17, 18, 21, 22, 23, 24, 25)
NEXT_STARS = (17, 22)
EOK = rc.EOK


@dataclass
class ShopTarget:
    slot: str
    item: str
    part: str
    star: int
    potential: str
    gain: float
    damage_pct: float
    craft_cost: float | None
    value_cap: float | None
    resale: float
    cap: float
    binding: str          # craft | value
    search: str
    detail: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    kind: str = "upgrade"          # upgrade(지금 장비와 같은 템) | next(다음 단계 템)
    level: int = 0
    base_price: float | None = None  # next: 노작 시세 (기록 없으면 None → 화면에서 입력)
    icon: str | None = None

    @property
    def cap_before_resale(self) -> float:
        return self.cap - self.resale

    def to_dict(self) -> dict:
        return {**self.__dict__, "cap_before_resale": self.cap_before_resale}


def threshold_from_plan(plan: dict) -> float | None:
    """예산 최적 조합에서 가장 효율 낮은 선택의 억당 환산 = 남은 돈의 기회비용."""
    vals = [c["per_eok"] for c in plan.get("chosen", []) if 0 < c["cost"] and c["per_eok"] < 1e11]
    return min(vals) if vals else None


def _lines_text(lines: list[dict]) -> str:
    return " / ".join(ln["text"] for ln in lines) or "없음"


def _pot_options(ctx: rc.Context, it: dict) -> list[tuple[str, hw.Delta, float, str | None]]:
    """(설명, 잠재 Delta, 추가 비용, 프리셋 id). 첫 항목은 현재 잠재 유지."""
    cur = gear.lines_delta(it["potential"], ctx.job, ctx.char_level)
    grade = it.get("potential_grade")
    out = [(f"잠재 현재 이상 ({_lines_text(it['potential'])})", cur, 0.0, None)]
    if not it["part"] or not grade:
        return out  # 잠재 없는 장비(시드링·특수 반지 등)는 잠재 목표 없음
    level, part = it["level"], it["part"]
    better = []
    for p in pt.presets(ctx.job_id, part, "potential", level):
        target = rc.preset_target(ctx, "potential", part, level, p["conditions"])
        if target is None or not rc.keeps_special(it, "potential", p["id"]):
            continue
        g, _ = rc._gain(ctx, cur, target)
        cost = _preset_cost(part, level, ctx.tickets.grade_start("potential", grade), p["conditions"])
        if g <= 1 or cost is None:
            continue
        better.append((g, (f"잠재 레전 {p['label']}", target, cost, p["id"])))
    better.sort(key=lambda x: x[0])  # 이득 작은 순 = 현실적인 목표부터
    return out + [b for _, b in better[:2]]


def _preset_cost(part: str, level: int, grade: str, conds) -> float | None:
    """잠재(윗잠) grade → 레전드리 등급업 + 목표 옵션까지 기대 메소 (메소 재설정 기준)."""
    try:
        stages = pt.grade_stages("potential", level, grade, "legendary")
        q = pt.option_probability("potential", part, level, conds)
    except (KeyError, ValueError):
        return None
    if q <= 0:
        return None
    return sum(s.expected_attempts * s.cost for s in stages) + pt.cost_per_attempt("potential", level, "legendary") / q


def _star_targets(it: dict) -> list[int]:
    part, start, level = it["part"], it["starforce"], it["level"]
    if (not part or part in rc.NO_STARFORCE or it["starforce_scroll"] or start <= 0 or level <= 0
            or any(k in it["name"] for k in load_items_config().get("no_starforce_keywords", []))):
        return [start]
    top = sf.max_star_for_level(level)
    return [start] + [t for t in STAR_TARGETS if start < t <= top][:3]


def _search_text(it: dict, star: int, pot_label: str) -> str:
    parts = [it["name"], f"{star}성 이상", pot_label]
    if it["additional"]:
        parts.append(f"에디 현재 이상 ({_lines_text(it['additional'])})")
    if it["part"] == "weapon" and it.get("weapon_flame_rank"):
        parts.append(f"공 {it['weapon_flame_rank']}추 이상")
    elif it.get("flame_score"):
        parts.append(f"추옵 {it['flame_score']:.0f}급 이상")
    return " · ".join(parts)


def targets_for_item(ctx: rc.Context, it: dict, listings: list[dict], threshold: float | None) -> list[ShopTarget]:
    if not it["part"] or not it["craftable"]:
        return []
    star0, level, part = it["starforce"], it["level"], it["part"]
    resale, _, why = mk.resale(listings, it, ctx.sell_fee)
    base_est = mk.base_price(listings, it["name"])
    spare = base_est.price if base_est else 0.0
    out = []
    for star in _star_targets(it):
        if star > star0:
            new, old, snotes = rc._star_pair(part, it, level, star)
            s0 = ctx.tickets.star_start(level, star0, star)
            try:
                exp = rc._sf_cost(ctx, level, s0, star, ctx.events, spare_price=spare, optimize=bool(spare))
            except ValueError:
                continue
            sf_cost, destroys = exp.total, exp.destroys
            if s0 != star0:
                snotes = snotes + [tk.note("star17")]
        else:
            new = old = hw.Delta()
            snotes, sf_cost, destroys = [], 0.0, 0.0
        for label, pdelta, pcost, pid in _pot_options(ctx, it):
            if star == star0 and pid is None:
                continue  # 현재와 같은 스펙
            cur_pot = gear.lines_delta(it["potential"], ctx.job, ctx.char_level)
            g, dp = rc._gain(ctx, old + cur_pot, new + pdelta)
            if g <= 1:
                continue
            craft = sf_cost + pcost
            value = g / threshold * EOK if threshold and threshold > 0 else None
            if value is not None and value < craft:
                cap, binding = value + resale, "value"
            else:
                cap, binding = craft + resale, "craft"
            notes = list(snotes)
            if destroys > 0.05:
                notes.append(f"직작 시 파괴 기대 {destroys:.2f}회"
                             + (f" (스페어 = 노작 시세 {spare / EOK:.2f}억 포함)" if spare
                                else " (스페어 비용 미포함 → 직작 비용·상한가가 낮게 잡힘)"))
            if pid and ctx.tickets.grade_start("potential", it.get("potential_grade")) != it.get("potential_grade"):
                notes.append(tk.note("potential"))
            notes.append(why or f"내 장비 되팔기 {resale / EOK:.2f}억 (수수료 {ctx.sell_fee:.0%} 차감)")
            out.append(ShopTarget(
                slot=it["slot"], item=it["name"], part=part, star=star, potential=label, gain=g, damage_pct=dp,
                craft_cost=craft, value_cap=value, resale=resale, cap=cap, binding=binding,
                search=_search_text(it, star, label),
                detail={"starforce": sf_cost, "potential": pcost, "destroys": destroys, "from_star": star0,
                        "preset_id": pid},
                notes=notes, level=level, icon=it.get("icon")))
    out.sort(key=lambda t: t.gain)
    return out


def _next_pots(ctx: rc.Context, it: dict, part: str, level: int) -> list[tuple[str, float]]:
    """다음 단계 템 잠재 목표: 잠재 무관 + 메소 기대 비용이 싼 레전 프리셋 2개 (지금 장비의 쿨감 등 유지)."""
    out = []
    for p in pt.presets(ctx.job_id, part, "potential", level):
        if not rc.keeps_special(it, "potential", p["id"]):
            continue
        cost = _preset_cost(part, level, ctx.tickets.grade_start("potential", "rare"), p["conditions"])
        if cost is not None:
            out.append((cost, f"잠재 레전 {p['label']}"))
    out.sort()
    return [("잠재 무관", 0.0)] + [(label, cost) for cost, label in out[:2]]


def next_targets(ctx: rc.Context, it: dict, listings: list[dict]) -> list[ShopTarget]:
    """장착 장비의 다음 단계 템 (노작 → 직작 기준 상한가)."""
    part = it["part"]
    if not part or not it["craftable"]:
        return []
    out = []
    for step in it.get("next_steps") or []:
        level, name = step["level"], step["name"]
        base = mk.base_price(listings, name) if name else None
        spare = base.price if base else 0.0
        top = sf.max_star_for_level(level)
        stars = sorted({s for s in (*NEXT_STARS, it["starforce"]) if 15 <= s <= top}) if part not in rc.NO_STARFORCE else [0]
        pots = _next_pots(ctx, it, part, level) if it.get("potential_grade") else [("잠재 무관", 0.0)]
        for star in stars:
            s0 = ctx.tickets.star_start(level, 0, star)
            try:
                exp = rc._sf_cost(ctx, level, s0, star, ctx.events, spare_price=spare, optimize=bool(spare)) \
                    if star else None
            except ValueError:
                continue
            sf_cost, destroys = (exp.total, exp.destroys) if exp else (0.0, 0.0)
            for label, pcost in pots:
                craft = sf_cost + pcost
                notes = []
                if destroys > 0.05:
                    notes.append(f"직작 시 파괴 기대 {destroys:.2f}회"
                                 + (" (스페어 = 노작 시세 포함)" if spare else " (스페어 비용 미포함 → 노작가를 넣으면 반영)"))
                if s0:
                    notes.append(tk.note("star17"))
                if pcost and ctx.tickets.grade_start("potential", "rare") != "rare":
                    notes.append(tk.note("potential"))
                notes.append("에디·추옵은 노작 수준 기준 (좋은 매물은 그만큼 더 쳐줄 수 있음)")
                out.append(ShopTarget(
                    slot=it["slot"], item=step["label"], part=part, star=star, potential=label, gain=0.0,
                    damage_pct=0.0, craft_cost=craft, value_cap=None, resale=0.0, cap=craft + spare, binding="craft",
                    search=" · ".join(x for x in (name or step["label"], f"{star}성 이상" if star else "", label) if x),
                    detail={"starforce": sf_cost, "potential": pcost, "destroys": destroys, "from_star": 0,
                            "sf_start": s0},
                    notes=notes, kind="next", level=level, base_price=base.price if base else None,
                    icon=f"/api/icon/{step['id']}" if step.get("id") else None))
    return out


def shopping_list(ctx: rc.Context, items: list[dict], listings: list[dict], threshold: float | None,
                  include_next: bool = True) -> list[ShopTarget]:
    out: list[ShopTarget] = []
    for it in items:
        out += targets_for_item(ctx, it, listings, threshold)
        if include_next:
            out += next_targets(ctx, it, listings)
    return out
