"""환산 주스탯 (데미지 공식 차분 방식).

D = (4·주스탯 + 부스탯) × 공격력 × (1 + 데미지% + 보공%) × (1 + 최종뎀%) × 방어율 항 × 크리 항
환산 Δ = ln(D'/D) / ln(D(주스탯 +1)/D)  → "최종 주스탯 몇 포인트와 같은가"
근거: docs/research/10_hwansan_logic.md §2.2, §5
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from functools import lru_cache

import yaml

from app.paths import GAME_DATA_DIR


@dataclass
class Assumptions:
    boss_armor: float = 300          # 보스 방어율 %
    crit_rate_100: bool = True       # 버프 포함 크확 100% 가정
    extra_main_pct: float = 0        # 장비 외 주스탯% (스킬 등)
    extra_att_pct: float = 0         # 장비 외 공격력%
    extra_main_static: float = 0     # 심볼·하이퍼 외 미적용 주스탯 (헥사 스탯 등)


@dataclass
class Spec:
    """캐릭터 최종 스탯과 그 분해. 주스탯 = 순수 × (1 + %) + 미적용."""
    main: float
    sub: float
    main_pct: float
    sub_pct: float
    main_static: float
    sub_static: float
    att: float
    att_pct: float
    dmg: float
    boss: float
    final_dmg: float
    ied: float
    crit_rate: float
    crit_dmg: float

    @property
    def main_pure(self) -> float:
        return (self.main - self.main_static) / (1 + self.main_pct / 100)

    @property
    def sub_pure(self) -> float:
        return (self.sub - self.sub_static) / (1 + self.sub_pct / 100)

    @property
    def att_pure(self) -> float:
        return self.att / (1 + self.att_pct / 100)


@dataclass
class Delta:
    """장비/옵션 변화량. 주스탯·부스탯 고정치는 % 적용을 받는다."""
    main: float = 0
    sub: float = 0
    main_pct: float = 0
    sub_pct: float = 0
    main_static: float = 0
    sub_static: float = 0
    att: float = 0
    att_pct: float = 0
    dmg: float = 0
    boss: float = 0
    final_dmg: float = 0   # 곱연산
    ied: float = 0         # 곱연산
    crit_rate: float = 0
    crit_dmg: float = 0
    notes: list[str] = field(default_factory=list)

    def __add__(self, o: "Delta") -> "Delta":
        out = Delta(**{k: getattr(self, k) + getattr(o, k) for k in _NUM_FIELDS})
        # 곱연산 항목은 합성
        out.final_dmg = ((1 + self.final_dmg / 100) * (1 + o.final_dmg / 100) - 1) * 100
        out.ied = (1 - (1 - self.ied / 100) * (1 - o.ied / 100)) * 100
        out.notes = self.notes + o.notes
        return out

    def scaled(self, k: float) -> "Delta":
        return Delta(**{f: getattr(self, f) * k for f in _NUM_FIELDS}, notes=list(self.notes))


_NUM_FIELDS = [f for f in Delta.__dataclass_fields__ if f != "notes"]


def apply(spec: Spec, d: Delta, sign: int = 1) -> Spec:
    """spec 에 d 를 더한(sign=1) 또는 뺀(sign=-1) 스펙."""
    s = sign
    main_pct = spec.main_pct + s * d.main_pct
    sub_pct = spec.sub_pct + s * d.sub_pct
    att_pct = spec.att_pct + s * d.att_pct
    main = (spec.main_pure + s * d.main) * (1 + main_pct / 100) + spec.main_static + s * d.main_static
    sub = (spec.sub_pure + s * d.sub) * (1 + sub_pct / 100) + spec.sub_static + s * d.sub_static
    att = (spec.att_pure + s * d.att) * (1 + att_pct / 100)
    fd_mult = 1 + d.final_dmg / 100
    ied_keep = 1 - d.ied / 100
    final_dmg = ((1 + spec.final_dmg / 100) * (fd_mult if s > 0 else 1 / fd_mult) - 1) * 100
    remain = 1 - spec.ied / 100
    ied = (1 - (remain * ied_keep if s > 0 else remain / ied_keep)) * 100
    return replace(
        spec, main=main, sub=sub, main_pct=main_pct, sub_pct=sub_pct,
        main_static=spec.main_static + s * d.main_static, sub_static=spec.sub_static + s * d.sub_static, att=att, att_pct=att_pct,
        dmg=spec.dmg + s * d.dmg, boss=spec.boss + s * d.boss, final_dmg=final_dmg, ied=ied,
        crit_rate=spec.crit_rate + s * d.crit_rate, crit_dmg=spec.crit_dmg + s * d.crit_dmg,
    )


def damage(spec: Spec, a: Assumptions) -> float:
    stat = 4 * spec.main + spec.sub
    dmg = 1 + (spec.dmg + spec.boss) / 100
    fd = 1 + spec.final_dmg / 100
    armor = max(0.0, 1 - a.boss_armor / 100 * (1 - spec.ied / 100))
    rate = 100 if a.crit_rate_100 else min(100, spec.crit_rate)
    crit = 1 + rate / 100 * (0.35 + spec.crit_dmg / 100)
    return stat * spec.att * dmg * fd * armor * crit


def unit_log(spec: Spec, a: Assumptions) -> float:
    """최종 주스탯 1 의 ln(D) 증가량 (환산 단위)."""
    return math.log(damage(replace(spec, main=spec.main + 1), a) / damage(spec, a))


def hwansan(spec: Spec, d: Delta, a: Assumptions, sign: int = 1) -> float:
    """d 를 더했을 때(sign=1) 또는 뺐을 때의 이득을 최종 주스탯 단위로. 빼면 잃는 양(양수)."""
    after = damage(apply(spec, d, sign), a)
    before = damage(spec, a)
    if after <= 0:
        return -math.inf if sign > 0 else math.inf
    gain = math.log(after / before) / unit_log(spec, a)
    return gain if sign > 0 else -gain


def damage_pct(spec: Spec, d: Delta, a: Assumptions) -> float:
    """d 를 더했을 때 보스 데미지 증가율(%)."""
    return (damage(apply(spec, d), a) / damage(spec, a) - 1) * 100


TABLE_ROWS = [
    ("주스탯 1 (최종)", Delta(main_static=1)),
    ("주스탯 1 (% 적용)", Delta(main=1)),
    ("주스탯 1%", Delta(main_pct=1)),
    ("올스탯 1%", Delta(main_pct=1, sub_pct=1)),
    ("부스탯 1 (% 적용)", Delta(sub=1)),
    ("공격력 1", Delta(att=1)),
    ("공격력 1%", Delta(att_pct=1)),
    ("데미지·보공 1%", Delta(boss=1)),
    ("최종 데미지 1%", Delta(final_dmg=1)),
    ("방어율 무시 1%", Delta(ied=1)),
    ("크리티컬 데미지 1%", Delta(crit_dmg=1)),
]


def table(spec: Spec, a: Assumptions) -> list[dict]:
    """현재 스펙 기준 1단위 환산표."""
    return [{"label": label, "hwansan": hwansan(spec, d, a), "damage_pct": damage_pct(spec, d, a)}
            for label, d in TABLE_ROWS]


# ---------------------------------------------------------------- 스타포스 스탯


@lru_cache(maxsize=1)
def load_star_stats() -> dict:
    with open(GAME_DATA_DIR / "star_stats.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _level_row(tbl: dict, level: int) -> dict | None:
    keys = [lv for lv in sorted(tbl) if lv <= level]
    return tbl[keys[-1]] if keys else None


def star_bonus(part: str, level: int, star: int, weapon_base_att: int = 0) -> tuple[float, float] | None:
    """성급 star 까지의 누적 (올스탯, 공/마). 표에 없는 구간이면 None."""
    cfg = load_star_stats()
    low = cfg["low_stat_per_star"]
    stat = sum(low[: min(star, 15)])
    if part == "weapon":
        att = 0
        cur = weapon_base_att
        for _ in range(min(star, 15)):
            inc = cur // 50 + 1
            att += inc
            cur += inc
        if star > 15:
            row = _level_row(cfg["weapon"], level)
            if not row or star not in row:
                return None
            att += row[star]
    else:
        att = sum(1 for s in cfg["gloves_att_stars"] if s <= star) if part == "gloves" else 0
        if star > 15:
            row = _level_row(cfg["armor"], level)
            if not row or star not in row:
                return None
            att += row[star][1]
    if star > 15:
        row = _level_row(cfg["armor"], level)
        if not row or star not in row:
            return None
        stat += row[star][0]
    return stat, att


def star_delta(part: str, level: int, start: int, target: int, weapon_base_att: int = 0) -> Delta | None:
    a, b = star_bonus(part, level, start, weapon_base_att), star_bonus(part, level, target, weapon_base_att)
    if a is None or b is None:
        return None
    return Delta(main=b[0] - a[0], sub=b[0] - a[0], att=b[1] - a[1])
