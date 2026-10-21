"""오픈 API 응답 → 계산기용 캐릭터/장비 구조."""

from __future__ import annotations

from functools import lru_cache

import yaml

from app.engine import flame as fl
from app.engine import gear
from app.engine import hwansan as hw
from app.engine import next_step as ns
from app.engine.potential import load_jobs, parse_option
from app.nexon import presets as pr
from app.nexon.client import NexonClient
from app.paths import GAME_DATA_DIR

GRADE_MAP = {"레어": "rare", "에픽": "epic", "유니크": "unique", "레전드리": "legendary"}
STAT_KEYS = {"STR": "str", "DEX": "dex", "INT": "int", "LUK": "luk"}


@lru_cache(maxsize=1)
def load_items_config() -> dict:
    with open(GAME_DATA_DIR / "items.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def is_boss_flame_item(name: str) -> bool:
    cfg = load_items_config()
    if any(k in name for k in cfg["non_boss_flame_keywords"]):
        return False
    return any(k in name for k in cfg["boss_flame_keywords"])


def is_craftable(name: str) -> bool:
    return not any(k in name for k in load_items_config().get("no_craft_keywords", []))


def job_for_class(character_class: str) -> str | None:
    return load_jobs().get("class_map", {}).get(character_class)


def flame_score(add: dict, job: dict, coef: fl.ScoreCoef) -> float:
    """방어구 추옵 급수 (주스탯 + 부스탯×b + 공×c + 올스탯%×d)."""
    main = _num(add.get(STAT_KEYS[job["main_stat"]]))
    sub = _num(add.get(STAT_KEYS[job["sub_stat"]]))
    att = _num(add.get("attack_power" if job["attack"] == "ATT" else "magic_power"))
    return main * coef.main + sub * coef.sub + att * coef.att + _num(add.get("all_stat")) * coef.all_pct


def weapon_flame_rank(item: dict, boss: bool) -> int | None:
    """무기 공격력 추옵이 몇 추인지 (1추 = 최고 단계). 해당 없으면 None."""
    base = int(_num(item["item_base_option"].get("attack_power")))
    level = int(_num(item["item_base_option"].get("base_equipment_level")))
    got = int(_num(item["item_add_option"].get("attack_power")))
    if not base or not got:
        return None
    for row in fl.weapon_attack_table(base, level, boss):
        if row["value"] == got:
            return row["rank"]
    return None


def att_field(job: dict) -> str:
    return "attack_power" if job["attack"] == "ATT" else "magic_power"


def parse_item(item: dict, job: dict, coef: fl.ScoreCoef) -> dict:
    slot = item["item_equipment_slot"]
    part = load_items_config()["slot_map"].get(slot)
    name = item["item_name"]
    boss = is_boss_flame_item(name)
    level = int(_num(item["item_base_option"].get("base_equipment_level")))

    def lines(prefix: str) -> list[dict]:
        out = []
        for i in (1, 2, 3):
            text = item.get(f"{prefix}_{i}")
            if text:
                key, val = parse_option(text)
                out.append({"text": text, "key": key, "value": val})
        return out

    add = item.get("item_add_option") or {}
    return {
        "slot": slot,
        "part": part,
        "name": name,
        "icon": item.get("item_icon"),
        "level": level,
        "starforce": int(_num(item.get("starforce"))),
        "starforce_scroll": item.get("starforce_scroll_flag") == "사용",  # 놀장
        "potential_grade": GRADE_MAP.get(item.get("potential_option_grade") or ""),
        "potential": lines("potential_option"),
        "additional_grade": GRADE_MAP.get(item.get("additional_potential_option_grade") or ""),
        "additional": lines("additional_potential_option"),
        "boss_flame": boss,
        "craftable": is_craftable(name),
        "flame": {k: v for k, v in add.items() if _num(v)},
        "flame_score": flame_score(add, job, coef) if part != "weapon" else None,
        "weapon_flame_rank": weapon_flame_rank(item, boss) if part == "weapon" else None,
        "cuttable_count": int(_num(item.get("cuttable_count"))) if item.get("cuttable_count") not in (None, "") else None,
        "scroll_upgrade": int(_num(item.get("scroll_upgrade"))),
        # 무기 1~15성 공 상승 계산용 (순수 + 주문서 공/마)
        "weapon_base_att": int(_num((item.get("item_base_option") or {}).get(att_field(job)))
                               + _num((item.get("item_etc_option") or {}).get(att_field(job)))),
        "weapon_base_att_pure": int(_num((item.get("item_base_option") or {}).get(att_field(job)))),
        "starforce_option": item.get("item_starforce_option"),
        "total_option": item.get("item_total_option"),
    }


def stat_attack_check(stats: dict[str, str], job: dict) -> dict:
    """최대 스탯공격력을 무기상수로 재계산해 직업 상수를 검증."""
    main, sub = _num(stats.get(job["main_stat"])), _num(stats.get(job["sub_stat"]))
    att = _num(stats.get("공격력" if job["attack"] == "ATT" else "마력"))
    calc = (job["weapon_constant"] * (4 * main + sub) * 0.01 * att
            * (1 + _num(stats.get("데미지")) / 100) * (1 + _num(stats.get("최종 데미지")) / 100))
    actual = _num(stats.get("최대 스탯공격력"))
    return {"calculated": calc, "actual": actual, "error_pct": (calc / actual - 1) * 100 if actual else None}


def load_character(name: str, *, refresh: bool = False, coef: fl.ScoreCoef | None = None,
                   assumptions: hw.Assumptions | None = None, client: NexonClient | None = None,
                   view: str = "current", choice: dict | None = None) -> dict:
    """view: current(착용 중) | boss | farming. choice: {"boss": {"equipment": n, "ability": n, "hyper": n}, "farming": {...}}
    (없으면 자동 추정)"""
    c = client or NexonClient()
    ocid = c.ocid(name, refresh=refresh)
    q = {"ocid": ocid}
    basic = c.get("/maplestory/v1/character/basic", q, refresh=refresh)
    stat = c.get("/maplestory/v1/character/stat", q, refresh=refresh)
    equip = c.get("/maplestory/v1/character/item-equipment", q, refresh=refresh)
    sets = c.get("/maplestory/v1/character/set-effect", q, refresh=refresh)
    symbols = c.get("/maplestory/v1/character/symbol-equipment", q, refresh=refresh)
    hyper = c.get("/maplestory/v1/character/hyper-stat", q, refresh=refresh)
    ability = c.get("/maplestory/v1/character/ability", q, refresh=refresh)

    job_id = job_for_class(basic["character_class"])
    job = load_jobs()["jobs"].get(job_id) if job_id else None
    stats = {s["stat_name"]: s["stat_value"] for s in stat["final_stat"]}
    coef = coef or fl.ScoreCoef()
    a = assumptions or hw.Assumptions()
    level = basic["character_level"]
    set_list = sets.get("set_effect", [])

    current = pr.current_presets(equip, ability, hyper)
    guessed = pr.guess(equip, ability, hyper)
    chosen = {k: {**guessed[k], **((choice or {}).get(k) or {})} for k in ("boss", "farming")}
    target = current if view == "current" else chosen[view]
    preset_info = {"current": current, "chosen": chosen, "guessed": guessed,
                   "custom": bool(choice), "view": view, "target": target}

    items: list[dict] = []
    analysis = None
    view_set_list = set_list
    if job:
        cur_items = [parse_item(i, job, coef) for i in equip["item_equipment"]]
        items = [parse_item(i, job, coef) for i in pr.preset_items_raw(equip, target["equipment"])] \
            if target["equipment"] != current["equipment"] else cur_items
        spec_cur, basis = gear.build_spec(stats, cur_items, symbols, hyper, job, a, level)
        members = load_items_config().get("set_members", {})
        view_set_list = pr.view_sets(set_list, [i["name"] for i in cur_items], [i["name"] for i in items], members)

        def total(its, sl, ab, hy):
            d = hw.Delta()
            for it in its:
                d = d + gear.item_delta(it, job, level)
            return (d + pr.sets_total(sl, members, job, level)
                    + pr.ability_delta(ability, ab, job) + pr.hyper_delta(hyper, hy, job))

        if target == current:
            spec = spec_cur
        else:
            spec = hw.apply(
                hw.apply(spec_cur, total(cur_items, set_list, current["ability"], current["hyper"]), -1),
                total(items, view_set_list, target["ability"], target["hyper"]))
            basis = {**basis, "item_main_pct": spec.main_pct - a.extra_main_pct,
                     "item_att_pct": spec.att_pct - a.extra_att_pct,
                     "hyper_main": spec.main_static - basis["symbol_main"] - a.extra_main_static,
                     "main_pure": spec.main_pure, "att_pure": spec.att_pure}
        analysis = analyze(spec, basis, items, view_set_list, job, level, a)
        for it in items:
            it["next_steps"] = ns.next_steps(it, job.get("class_type")) if it["part"] and it["craftable"] else []
        missing = [s["set_name"] for s in view_set_list if s.get("missing_options")]
        if missing:
            analysis["warnings"] = [f"세트 효과 수치를 몰라 제외: {', '.join(missing)}"]

    return {
        "name": basic["character_name"],
        "world": basic["world_name"],
        "class": basic["character_class"],
        "level": basic["character_level"],
        "image": basic.get("character_image"),
        "job_id": job_id,
        "supported": job is not None,
        "stats": stats,
        "constant_check": stat_attack_check(stats, job) if job else None,
        "items": items,
        "set_effects": [{"name": s["set_name"], "count": s["total_set_count"]} for s in view_set_list],
        "presets": preset_info,
        "hwansan": analysis,
    }


def analyze(spec: hw.Spec, basis: dict, items: list[dict], sets: list[dict], job: dict,
            level: int, a: hw.Assumptions) -> dict:
    """1단위 환산표 + 장비별 기여(세트 포함)를 items 에 기록."""
    members = load_items_config().get("set_members", {})
    for it in items:
        own = gear.item_delta(it, job, level)
        sets_lost = gear.set_loss(it["name"], sets, members, job, level)
        it["hwansan"] = hw.hwansan(spec, own + sets_lost, a, sign=-1)
        it["hwansan_set"] = it["hwansan"] - hw.hwansan(spec, own, a, sign=-1)
    return {
        "spec": spec.__dict__,
        "basis": basis,
        "assumptions": a.__dict__,
        "table": hw.table(spec, a),
        "warnings": [],
    }
