"""장비·잠재·세트 → 환산 Delta, 오픈 API 스탯 → Spec 분해."""

from __future__ import annotations

import re

from app.engine.hwansan import Assumptions, Delta, Spec
from app.engine.potential import parse_option

STAT_FIELD = {"STR": "str", "DEX": "dex", "INT": "int", "LUK": "luk"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def line_delta(key: str, value: float, job: dict, char_level: int) -> Delta:
    """잠재/에디/세트 옵션 1줄."""
    main, sub = job["main_stat"], job["sub_stat"]
    att = "ATT" if job["attack"] == "ATT" else "MATT"
    if key == f"{main}%":
        return Delta(main_pct=value)
    if key == f"{sub}%":
        return Delta(sub_pct=value)
    if key == "ALL%":
        return Delta(main_pct=value, sub_pct=value)
    if key == main:
        return Delta(main=value)
    if key == sub:
        return Delta(sub=value)
    if key == "ALL":
        return Delta(main=value, sub=value)
    if key == f"{main}/9LV":
        return Delta(main=value * (char_level // 9))
    if key == f"{sub}/9LV":
        return Delta(sub=value * (char_level // 9))
    if key == att:
        return Delta(att=value)
    if key == f"{att}%":
        return Delta(att_pct=value)
    if key == "BOSS%":
        return Delta(boss=value)
    if key == "DMG%":
        return Delta(dmg=value)
    if key == "IED%":
        return Delta(ied=value)
    if key == "CRIT_DMG":
        return Delta(crit_dmg=value)
    if key == "CRIT_RATE":
        return Delta(crit_rate=value)
    return Delta()


def lines_delta(lines: list[dict], job: dict, char_level: int) -> Delta:
    total = Delta()
    for ln in lines:
        total = total + line_delta(ln["key"], ln["value"], job, char_level)
    return total


def option_dict_delta(opt: dict, job: dict) -> Delta:
    """item_total_option 형식 (고정 수치 + all_stat% 등)."""
    att_key = "attack_power" if job["attack"] == "ATT" else "magic_power"
    return Delta(
        main=_num(opt.get(STAT_FIELD[job["main_stat"]])),
        sub=_num(opt.get(STAT_FIELD[job["sub_stat"]])),
        main_pct=_num(opt.get("all_stat")),
        sub_pct=_num(opt.get("all_stat")),
        att=_num(opt.get(att_key)),
        boss=_num(opt.get("boss_damage")),
        dmg=_num(opt.get("damage")),
        ied=_num(opt.get("ignore_monster_armor")),
    )


def item_delta(item: dict, job: dict, char_level: int) -> Delta:
    """parse_item 결과 1개 장비의 전체 기여 (스타포스·추옵·주문서·잠재·에디 포함)."""
    return (option_dict_delta(item.get("total_option") or {}, job)
            + lines_delta(item["potential"], job, char_level)
            + lines_delta(item["additional"], job, char_level))


# ---------------------------------------------------------------- 세트 효과


def parse_set_option(text: str, job: dict, char_level: int) -> Delta:
    total = Delta()
    for part in text.split(","):
        clean = re.sub(r"\s+", " ", part.strip()).replace(" : ", " ")
        key, val = parse_option(clean)
        total = total + line_delta(key, val, job, char_level)
    return total


def set_bonus(full: list[dict], count: int, job: dict, char_level: int) -> Delta:
    """set_option_full 에서 count 개 착용 시 활성 효과 합."""
    total = Delta()
    for tier in full:
        if tier["set_count"] <= count:
            total = total + parse_set_option(tier["set_option"], job, char_level)
    return total


def item_sets(name: str, members: dict[str, list[str]]) -> list[str]:
    return [s for s, kws in members.items() if any(k in name for k in kws)]


def set_loss(name: str, sets: list[dict], members: dict[str, list[str]], job: dict, char_level: int) -> Delta:
    """이 장비를 빼면 잃는 세트 효과 (sets = API set_effect)."""
    out = Delta()
    for key in item_sets(name, members):
        for st in sets:
            if key in st["set_name"]:
                n = st["total_set_count"]
                full = st.get("set_option_full") or []
                if n <= 0:
                    continue
                lost = set_bonus(full, n, job, char_level)
                kept = set_bonus(full, n - 1, job, char_level)
                out = out + _subtract(lost, kept)
    return out


def _subtract(a: Delta, b: Delta) -> Delta:
    d = a + b.scaled(-1)
    d.final_dmg = ((1 + a.final_dmg / 100) / (1 + b.final_dmg / 100) - 1) * 100
    d.ied = (1 - (1 - a.ied / 100) / (1 - b.ied / 100)) * 100
    return d


# ---------------------------------------------------------------- 스펙 분해


def hyper_stat(hyper: dict, stat: str) -> float:
    preset = hyper.get(f"hyper_stat_preset_{hyper.get('use_preset_no') or 1}") or []
    for row in preset:
        if row["stat_type"] == stat and row.get("stat_increase"):
            m = re.search(r"(\d+)", row["stat_increase"])
            return float(m.group(1)) if m else 0.0
    return 0.0


def symbol_stat(symbols: dict, stat: str) -> float:
    return sum(_num(s.get(f"symbol_{STAT_FIELD[stat]}")) for s in symbols.get("symbol", []))


def build_spec(stats: dict[str, str], items: list[dict], symbols: dict, hyper: dict, job: dict,
               a: Assumptions, char_level: int) -> tuple[Spec, dict]:
    """최종 스탯 + 장비 % 합계로 순수/%/미적용 분해. 반환: (Spec, 분해 근거)"""
    main, sub = job["main_stat"], job["sub_stat"]
    item_main_pct = item_sub_pct = item_att_pct = 0.0
    for it in items:
        d = item_delta(it, job, char_level)
        item_main_pct += d.main_pct
        item_sub_pct += d.sub_pct
        item_att_pct += d.att_pct
    sym_main, sym_sub = symbol_stat(symbols, main), symbol_stat(symbols, sub)
    hyp_main, hyp_sub = hyper_stat(hyper, main), hyper_stat(hyper, sub)
    att_name = "공격력" if job["attack"] == "ATT" else "마력"
    spec = Spec(
        main=_num(stats.get(main)), sub=_num(stats.get(sub)),
        main_pct=item_main_pct + a.extra_main_pct, sub_pct=item_sub_pct,
        main_static=sym_main + hyp_main + a.extra_main_static, sub_static=sym_sub + hyp_sub,
        att=_num(stats.get(att_name)), att_pct=item_att_pct + a.extra_att_pct,
        dmg=_num(stats.get("데미지")), boss=_num(stats.get("보스 몬스터 데미지")),
        final_dmg=_num(stats.get("최종 데미지")), ied=_num(stats.get("방어율 무시")),
        crit_rate=_num(stats.get("크리티컬 확률")), crit_dmg=_num(stats.get("크리티컬 데미지")),
    )
    basis = {
        "item_main_pct": item_main_pct, "item_att_pct": item_att_pct,
        "symbol_main": sym_main, "hyper_main": hyp_main,
        "main_pure": spec.main_pure, "att_pure": spec.att_pure,
    }
    return spec, basis
