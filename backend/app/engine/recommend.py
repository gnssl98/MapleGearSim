"""업그레이드 후보 생성 → 억당 환산 랭킹 → 예산 최적 조합.

후보 종류
- starforce: 현재 성 → 목표 성 (기대 비용, 샤타포스 대기 시 비용)
- potential / additional: 프리셋 목표 달성 (등급 상승 + 옵션 기대 비용)
- flame: 방어구 추옵 급수 목표 / 무기 공 n추 목표
- buy: 기록된 매물 구매 (+ 구매 후 스타포스 = 혼합 전략), 기존 장비 되팔기 차감
- base: 노작 매물 구매 + 스타포스·잠재·추옵 직작, 기존 장비 되팔기 차감
이득은 모두 환산 주스탯(hwansan.py) 기준이며, 같은 장비의 여러 강화는 이득을 더해서 근사한다.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np

from app.engine import compare as cmp
from app.engine import flame as fl
from app.engine import gear
from app.engine import hwansan as hw
from app.engine import market as mk
from app.engine import potential as pt
from app.engine import starforce as sf
from app.engine import tickets as tk
from app.nexon.character import load_items_config

EOK = 100_000_000
SF_TARGETS = (17, 18, 19, 20, 21, 22, 23, 24, 25)
NO_FLAME = {"ring", "shoulder", "emblem", "secondary", "shield", "force_shield", "heart"}
PURCHASE_KINDS = {"buy", "base"}  # 슬롯 장비 자체를 바꾸는 후보 (기존 장비 강화와 동시 선택 불가)
NO_STARFORCE = {"emblem", "secondary", "shield", "force_shield"}


@dataclass
class Context:
    spec: hw.Spec
    a: hw.Assumptions
    job_id: str
    job: dict
    char_level: int
    mvp: str = "none"
    pc_room: bool = False
    mvp_max_star: int | None = None
    events: sf.Events = field(default_factory=sf.Events)
    coef: fl.ScoreCoef = field(default_factory=fl.ScoreCoef)
    flame_method: str = "meso_reset"
    sell_fee: float = 0.05
    tickets: tk.Tickets = field(default_factory=tk.Tickets)


@dataclass
class Candidate:
    slot: str
    item: str
    kind: str          # starforce | potential | additional | flame | buy
    label: str
    gain: float        # 환산 주스탯
    damage_pct: float  # 보스 데미지 증가율 %
    cost: float        # 기대 비용 (메소)
    detail: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def per_eok(self) -> float:
        # 되팔기 차익으로 비용이 0 이하면 "돈을 벌면서 오름" → 최상위
        return self.gain / (self.cost / EOK) if self.cost > 0 else 1e12

    def to_dict(self) -> dict:
        return {**self.__dict__, "per_eok": self.per_eok}


def _gain(ctx: Context, remove: hw.Delta, add: hw.Delta) -> tuple[float, float]:
    """remove 를 빼고 add 를 넣었을 때 (환산, 데미지%)."""
    base = hw.damage(ctx.spec, ctx.a)
    after = hw.damage(hw.apply(hw.apply(ctx.spec, remove, -1), add), ctx.a)
    if after <= 0:
        return -math.inf, -100.0
    return math.log(after / base) / hw.unit_log(ctx.spec, ctx.a), (after / base - 1) * 100


# ---------------------------------------------------------------- 스타포스


def _sf_cost(ctx: Context, level: int, start: int, target: int, events: sf.Events,
             spare_price: float = 0.0, optimize: bool = False) -> sf.Expectation:
    if start >= target:  # 17성 강화권으로 목표에 바로 도달
        return sf.Expectation(meso=0.0, attempts=0.0, destroys=0.0, spares=0.0, total=0.0)
    inp = sf.StarforceInput(level=level, start=start, target=target, mvp=ctx.mvp, pc_room=ctx.pc_room,
                            mvp_max_star=ctx.mvp_max_star, events=events, spare_price=spare_price)
    if optimize:  # 스페어 시세를 알 때만 의미 있음: 파방·복구 최적 정책
        inp = sf.with_policy(inp, sf.optimize_policy(inp))
    return sf.expected(inp)[0]


def starforce_candidates(ctx: Context, it: dict, start: int | None = None, level: int | None = None,
                         max_targets: int = 4) -> list[Candidate]:
    part = it["part"]
    if not part or part in NO_STARFORCE or not it["craftable"] or it["starforce_scroll"]:
        return []
    if any(k in it["name"] for k in load_items_config().get("no_starforce_keywords", [])):
        return []
    level = level or it["level"]
    start = it["starforce"] if start is None else start
    if start <= 0 or level <= 0:
        return []  # 0성 장비는 강화 불가 장비(시드링 등)가 많아 제외
    top = sf.max_star_for_level(level)
    out = []
    shining = sf.Events.shining()
    for t in [t for t in SF_TARGETS if start < t <= top][:max_targets]:
        d = hw.star_delta(part, level, start, t, it.get("weapon_base_att", 0))
        if d is None:
            continue
        g, dp = _gain(ctx, hw.Delta(), d)
        s0 = ctx.tickets.star_start(level, start, t)
        exp = _sf_cost(ctx, level, s0, t, ctx.events)
        detail = {"start": start, "target": t, "level": level, "destroys": exp.destroys, "attempts": exp.attempts,
                  "stat": d.main, "att": d.att}
        if not (ctx.events.discount30 and ctx.events.destroy_reduction):
            ev = _sf_cost(ctx, level, s0, t, shining)
            detail["event_cost"] = ev.total
            detail["event_destroys"] = ev.destroys
        notes = [f"파괴 기대 {exp.destroys:.2f}회 (스페어 비용 미포함)"] if exp.destroys > 0.05 else []
        if s0 != start:
            notes.append(tk.note("star17"))
        out.append(Candidate(it["slot"], it["name"], "starforce", f"{start}→{t}성", g, dp, exp.total, detail, notes))
    return out


# ---------------------------------------------------------------- 잠재 / 에디


def top_value(kind: str, part: str, level: int, key: str) -> float:
    """레전드리 첫 줄에서 key 옵션의 최대 수치."""
    try:
        lines = pt.load_option_tables()["tables"][pt._table_key(kind, "legendary", part, level)]
    except KeyError:
        return 0.0
    vals = [pt.parse_option(r["option"]) for r in lines[0]]
    return max((v for k, v in vals if k == key), default=0.0)


def preset_target(ctx: Context, kind: str, part: str, level: int, conds: list[pt.Condition]) -> hw.Delta | None:
    """프리셋 조건을 겨우 만족하는 결과를 Delta 로 (보수적). 표현 못 하는 조건이면 None."""
    total = hw.Delta()
    main = ctx.job["main_stat"]
    for c in conds:
        keys = set(c.keys)
        if c.mode == "sum" and keys <= {f"{main}%", "ALL%"}:
            total = total + hw.Delta(main_pct=c.min)
        elif c.mode == "count" and len(keys) == 1:
            key = next(iter(keys))
            v = top_value(kind, part, level, key)
            if not v:
                return None
            for _ in range(int(c.min)):
                total = total + gear.line_delta(key, v, ctx.job, ctx.char_level)
        else:
            return None
    return total


def keeps_special(it: dict, kind: str, preset_id: str) -> bool:
    """환산에 안 잡히는 옵션(쿨감)을 일부러 띄운 장비는 같은 종류 목표만 허용."""
    lines = it["potential"] if kind == "potential" else it["additional"]
    return not any(ln["key"] == "CDR" for ln in lines) or preset_id.startswith("cdr")


def potential_candidates(ctx: Context, it: dict, kind: str) -> list[Candidate]:
    part = it["part"]
    grade = it["potential_grade"] if kind == "potential" else it["additional_grade"]
    if not part or not it["craftable"] or not grade:
        return []
    current = gear.lines_delta(it[kind], ctx.job, ctx.char_level)
    level = it["level"]
    out = []
    for p in pt.presets(ctx.job_id, part, kind, level):
        target = preset_target(ctx, kind, part, level, p["conditions"])
        if target is None or not keeps_special(it, kind, p["id"]):
            continue
        g, dp = _gain(ctx, current, target)
        if g <= 1:
            continue
        try:
            g0 = ctx.tickets.grade_start(kind, grade)
            stages = pt.grade_stages(kind, level, g0, "legendary")
            q = pt.option_probability(kind, part, level, p["conditions"])
        except (KeyError, ValueError):
            continue
        if q <= 0:
            continue
        cost = sum(s.expected_attempts * s.cost for s in stages) + pt.cost_per_attempt(kind, level, "legendary") / q
        notes = ["목표를 겨우 만족하는 결과로 이득 계산 (보수적)"] + ([tk.note(kind)] if g0 != grade else [])
        out.append(Candidate(it["slot"], it["name"], kind, p["label"], g, dp, cost,
                             {"prob": q, "preset_id": p["id"], "grade_up": bool(stages)}, notes))
    return out


# ---------------------------------------------------------------- 추옵


def flame_candidates(ctx: Context, it: dict, dist_cache: dict, keep: int = 3) -> list[Candidate]:
    part = it["part"]
    if not part or not it["craftable"] or part in NO_FLAME or it["level"] <= 0:
        return []
    method = ctx.flame_method
    try:
        cost1 = fl.cost_per_attempt(method)
    except ValueError:
        return []
    out = []
    if part == "weapon":
        rank = it.get("weapon_flame_rank")
        base = it.get("weapon_base_att_pure") or 0
        if not base:
            return []
        table = fl.weapon_attack_table(base, it["level"], it["boss_flame"])
        cur_val = next((r["value"] for r in table if r["rank"] == rank), 0)
        for row in table[:2]:
            if rank is not None and row["rank"] >= rank:
                continue
            q = fl.weapon_probability(it["boss_flame"], method, {"ATT": row["tier"]})
            if q <= 0:
                continue
            g, dp = _gain(ctx, hw.Delta(), hw.Delta(att=row["value"] - cur_val))
            out.append(Candidate(it["slot"], it["name"], "flame", f"공 {row['rank']}추 (+{row['value'] - cur_val})",
                                 g, dp, cost1 / q, {"prob": q, "rank": row["rank"]},
                                 ["공격력 추옵만 반영 (보공·데미지 추옵 변화 미반영)"]))
        return out

    score = it.get("flame_score") or 0
    key = (it["level"], it["boss_flame"])
    if key not in dist_cache:
        j = ctx.job
        dist_cache[key] = fl.score_distribution(it["level"], it["boss_flame"], method, j["main_stat"], j["sub_stat"],
                                                j["attack"], ctx.coef)
    dist = dist_cache[key]
    t = math.floor(score / 10) * 10 + 10
    for _ in range(40):
        q = fl.prob_score_at_least(dist, t)
        if q < 2e-4:
            break
        g, dp = _gain(ctx, hw.Delta(), hw.Delta(main=(t - score) * ctx.coef.main))
        out.append(Candidate(it["slot"], it["name"], "flame", f"{num0(score)}→{t}급", g, dp, cost1 / q,
                             {"prob": q, "target": t}, ["급수 차이를 % 적용 주스탯으로 환산 (급수 계수 기준)"]))
        t += 10
    out.sort(key=lambda c: -c.per_eok)
    return out[:keep]


def num0(v: float) -> str:
    return f"{v:.0f}"


# ---------------------------------------------------------------- 매물 구매


def _listing_lines(row: dict, prefix: str) -> list[dict]:
    out = []
    for i in (1, 2, 3):
        text = (row.get(f"{prefix}{i}") or "").strip()
        if text:
            k, v = pt.parse_option(text)
            out.append({"text": text, "key": k, "value": v})
    return out


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _weakest(items: list[dict], part: str) -> dict | None:
    """같은 부위가 여럿(반지·펜던트)이면 기여가 가장 낮은 장비를 교체 대상으로."""
    same = [it for it in items if it["part"] == part]
    return min(same, key=lambda it: it.get("hwansan", 0)) if same else None


def _resale(ctx: Context, cur: dict, listings: list[dict]) -> tuple[float, list[str]]:
    net, _, why = mk.resale(listings, cur, ctx.sell_fee)
    return net, ([why] if why else [f"기존 장비 되팔기 {net / EOK:.2f}억 차감 (수수료 {ctx.sell_fee:.0%})"])


def _star_pair(part: str, cur: dict, level: int, star: int) -> tuple[hw.Delta, hw.Delta, list[str]]:
    new = hw.star_delta(part, level, 0, star, cur.get("weapon_base_att", 0)) if star else hw.Delta()
    old = hw.star_delta(part, cur["level"], 0, cur["starforce"], cur.get("weapon_base_att", 0)) \
        if cur["starforce"] else hw.Delta()
    if new is None or old is None:
        return hw.Delta(), hw.Delta(), ["스타포스 스탯 표에 없는 구간 (스타포스 차이 미반영)"]
    return new, old, []


def buy_candidates(ctx: Context, items: list[dict], listings: list[dict]) -> list[Candidate]:
    out = []
    for row in listings:
        part = row.get("slot")
        price = _f(row.get("price_meso"))
        if not part or not price or mk.is_base(row):
            continue
        cur = _weakest(items, part)
        if not cur:
            continue
        level = int(_f(row.get("item_level")) or cur["level"])
        star = int(_f(row.get("star")) or 0)
        star_d, cur_star, notes = _star_pair(part, cur, level, star)
        new_pot = gear.lines_delta(_listing_lines(row, "pot"), ctx.job, ctx.char_level)
        new_add = gear.lines_delta(_listing_lines(row, "add"), ctx.job, ctx.char_level)
        old_pot = gear.lines_delta(cur["potential"], ctx.job, ctx.char_level)
        old_add = gear.lines_delta(cur["additional"], ctx.job, ctx.char_level)
        fs = _f(row.get("flame_score"))
        flame_d = hw.Delta(main=(fs - (cur.get("flame_score") or 0)) * ctx.coef.main) \
            if fs is not None and part != "weapon" else hw.Delta()
        if row.get("item_name", "").strip() != cur["name"]:
            notes.append(f"현재 장비({cur['name']})와 아이템이 달라 기본 스탯·세트 효과 차이는 미반영")
        g, dp = _gain(ctx, cur_star + old_pot + old_add, star_d + new_pot + new_add + flame_d)
        resale_net, rnotes = _resale(ctx, cur, listings)
        cost = cmp.effective_buy_price(price, row.get("world_type") == "other") - resale_net
        label = f"매물 {row.get('item_name')} {star}성"
        detail = {"listing_id": row.get("id"), "observed_at": row.get("observed_at"), "price": price,
                  "resale": resale_net}
        out.append(Candidate(cur["slot"], cur["name"], "buy", label, g, dp, cost, detail, notes + rnotes))
        # 혼합 전략: 매물 구매 후 직접 스타포스
        fake = {**cur, "level": level, "starforce": star, "craftable": True, "starforce_scroll": False}
        for c in starforce_candidates(ctx, fake, max_targets=3):
            out.append(Candidate(cur["slot"], cur["name"], "buy", f"{label} + {c.label}", g + c.gain,
                                 dp + c.damage_pct, cost + c.cost, {**detail, "then_starforce": c.detail},
                                 notes + rnotes + c.notes))
    return out


def base_candidates(ctx: Context, items: list[dict], listings: list[dict], dist_cache: dict) -> list[Candidate]:
    """노작(베이스) 매물을 사서 스타포스·잠재·추옵을 직접 맞추고 기존 장비는 판다.
    추옵은 기존 장비 급수와 같게, 에디는 없음(기존 에디 손실 반영)으로 둔다."""
    out = []
    seen = set()
    for row in listings:
        part = row.get("slot")
        if not part or not mk.is_base(row) or not _f(row.get("price_meso")):
            continue
        cur = _weakest(items, part)
        if not cur or not cur["part"]:
            continue
        name = row["item_name"].strip()
        if (cur["slot"], name) in seen:
            continue  # 같은 아이템 노작 매물이 여럿이면 시세(중앙값) 하나로
        seen.add((cur["slot"], name))
        est = mk.base_price(listings, name)
        base = est.price if est else mk.eff_price(row)
        level = int(_f(row.get("item_level")) or cur["level"])
        boss = cur["boss_flame"] if name == cur["name"] else False
        notes = [] if name == cur["name"] else [f"현재 장비({cur['name']})와 아이템이 달라 기본 스탯·세트 효과 차이는 미반영"]
        resale_net, rnotes = _resale(ctx, cur, listings)
        notes += rnotes + [f"노작 {est.n if est else 1}건 시세 {base / EOK:.2f}억"]

        # 추옵: 기존 급수 이상 맞추기 (못 맞추면 추옵 없음으로 손실 반영)
        flame_cost, flame_d, fnote = 0.0, hw.Delta(main=-(cur.get("flame_score") or 0) * ctx.coef.main), None
        score = cur.get("flame_score") or 0
        if part not in NO_FLAME and part != "weapon" and score > 0:
            key = (level, boss)
            if key not in dist_cache:
                j = ctx.job
                dist_cache[key] = fl.score_distribution(level, boss, ctx.flame_method, j["main_stat"], j["sub_stat"],
                                                        j["attack"], ctx.coef)
            q = fl.prob_score_at_least(dist_cache[key], score)
            if q >= 1e-4:
                flame_cost, flame_d = fl.cost_per_attempt(ctx.flame_method) / q, hw.Delta()
                fnote = f"추옵 {score:.0f}급 이상"
        elif part == "weapon":
            flame_d = hw.Delta()
            notes.append("무기 추옵은 기존과 같다고 가정 (비용 미포함)")

        old_pot = gear.lines_delta(cur["potential"], ctx.job, ctx.char_level)
        old_add = gear.lines_delta(cur["additional"], ctx.job, ctx.char_level)
        presets = [p for p in pt.presets(ctx.job_id, part, "potential", level)
                   if preset_target(ctx, "potential", part, level, p["conditions"]) is not None]
        pot_opts = []
        for p in presets:
            try:
                q = pt.option_probability("potential", part, level, p["conditions"])
                stages = pt.grade_stages("potential", level, ctx.tickets.grade_start("potential", "rare"), "legendary")
            except (KeyError, ValueError):
                continue
            if q > 0:
                cost = sum(s.expected_attempts * s.cost for s in stages) + pt.cost_per_attempt("potential", level, "legendary") / q
                pot_opts.append((p, preset_target(ctx, "potential", part, level, p["conditions"]), cost))
        pot_opts = sorted(pot_opts, key=lambda x: x[2])[:3]
        top = sf.max_star_for_level(level)
        stars = [t for t in (17, 18, 22) if t <= top]
        for t in stars:
            star_d, cur_star, snotes = _star_pair(part, cur, level, t)
            s0 = ctx.tickets.star_start(level, 0, t)
            exp = _sf_cost(ctx, level, s0, t, ctx.events, spare_price=base, optimize=True)
            tnotes = ([tk.note("star17")] if s0 else []) + \
                ([tk.note("potential")] if ctx.tickets.grade_start("potential", "rare") != "rare" else [])
            for p, pdelta, pcost in pot_opts:
                g, dp = _gain(ctx, cur_star + old_pot + old_add, star_d + pdelta + flame_d)
                cost = base + exp.total + pcost + flame_cost - resale_net
                label = f"노작 {name} → {t}성 · {p['label']}" + (f" · {fnote}" if fnote else "")
                out.append(Candidate(cur["slot"], cur["name"], "base", label, g, dp, cost,
                                     {"base_price": base, "starforce": exp.total, "potential": pcost,
                                      "flame": flame_cost, "resale": resale_net, "destroys": exp.destroys},
                                     notes + snotes + tnotes + ["에디 없음 (기존 에디 손실 반영)",
                                                       f"파괴 기대 {exp.destroys:.2f}회 (스페어 = 노작 시세, 파방·복구 최적 정책)"]))
    return out


# ---------------------------------------------------------------- 예산 최적화


def optimize_budget(cands: list[Candidate], budget: float, unit: float = 1e7, per_kind: int = 4) -> dict:
    """슬롯별로 (구매 1개) 또는 (강화 종류별 최대 1개 조합) 중 하나를 골라 예산 내 환산 합 최대화.
    다중 선택 배낭 DP. unit = 비용 이산화 단위(기본 0.1억)."""
    n = int(budget // unit)
    if n <= 0:
        return {"chosen": [], "gain": 0.0, "cost": 0.0}
    by_slot: dict[str, list[Candidate]] = {}
    for c in cands:
        if c.gain > 0 and math.isfinite(c.cost):
            by_slot.setdefault(c.slot, []).append(c)

    groups: list[list[tuple[int, float, list[Candidate]]]] = []
    for slot_cands in by_slot.values():
        kinds: dict[str, list[Candidate]] = {}
        for c in slot_cands:
            if c.kind not in PURCHASE_KINDS:
                kinds.setdefault(c.kind, []).append(c)
        per = [[None] + sorted(v, key=lambda c: -c.per_eok)[:per_kind] for v in kinds.values()]
        opts = []
        for combo in itertools.product(*per):
            chosen = [c for c in combo if c is not None]
            if chosen:
                opts.append(chosen)
        opts += [[c] for c in sorted((c for c in slot_cands if c.kind in PURCHASE_KINDS), key=lambda c: -c.per_eok)[:per_kind * 3]]
        g = []
        for chosen in opts:
            cost_units = max(0, math.ceil(sum(c.cost for c in chosen) / unit))  # 되팔기로 음수 가능
            if cost_units <= n:
                g.append((cost_units, sum(c.gain for c in chosen), chosen))
        if g:
            groups.append(g)

    best = np.zeros(n + 1)
    picks = []
    for g in groups:
        new = best.copy()
        arg = np.full(n + 1, -1)
        for idx, (cu, gain, _) in enumerate(g):
            cand = np.full(n + 1, -np.inf)
            cand[cu:] = best[: n + 1 - cu] + gain
            better = cand > new
            new[better] = cand[better]
            arg[better] = idx
        picks.append(arg)
        best = new

    chosen: list[Candidate] = []
    b = n
    for g, arg in zip(reversed(groups), reversed(picks)):
        idx = arg[b]
        if idx >= 0:
            cu, _, cs = g[idx]
            chosen.extend(cs)
            b -= cu
    chosen.sort(key=lambda c: -c.per_eok)
    return {"chosen": [c.to_dict() for c in chosen], "gain": float(sum(c.gain for c in chosen)),
            "cost": float(sum(c.cost for c in chosen))}


def generate(ctx: Context, items: list[dict], listings: list[dict]) -> list[Candidate]:
    cands: list[Candidate] = []
    dist_cache: dict = {}
    for it in items:
        cands += starforce_candidates(ctx, it)
        cands += potential_candidates(ctx, it, "potential")
        cands += potential_candidates(ctx, it, "additional")
        cands += flame_candidates(ctx, it, dist_cache)
    cands += buy_candidates(ctx, items, listings)
    cands += base_candidates(ctx, items, listings, dist_cache)
    cands = [c for c in cands if c.gain > 0]
    cands.sort(key=lambda c: -c.per_eok)
    return cands
