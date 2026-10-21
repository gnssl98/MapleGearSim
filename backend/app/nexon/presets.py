"""캐릭터 프리셋(장비·어빌리티·하이퍼스탯) → 보스용/재획용 스펙.

오픈 API 최종 스탯은 "현재 착용 중인" 프리셋 기준이다. 다른 프리셋의 스펙은
현재 스펙에서 (현재 장비+세트+어빌+하이퍼) 기여를 빼고 (대상 프리셋의 것) 을 더해 추정한다.
링크 스킬·유니온 프리셋 차이는 반영하지 않는다.
"""

from __future__ import annotations

import re
from functools import lru_cache

import yaml

from app.engine import gear
from app.engine import hwansan as hw
from app.paths import GAME_DATA_DIR

KINDS = ("equipment", "ability", "hyper")
STAT_WORD = {"힘": "STR", "민첩성": "DEX", "지능": "INT", "운": "LUK"}
FARM_WORDS = ("메소 획득량", "아이템 드롭률")


@lru_cache(maxsize=1)
def load_set_catalog() -> dict:
    path = GAME_DATA_DIR / "sets.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {name: [{"set_count": t["count"], "set_option": t["option"]} for t in tiers] for name, tiers in data.items()}


# ---------------------------------------------------------------- 어빌리티 / 하이퍼 문장 파싱


def _stat(job: dict, stat: str, v: float, static: bool) -> hw.Delta:
    if stat == job["main_stat"]:
        return hw.Delta(main_static=v) if static else hw.Delta(main=v)
    if stat == job["sub_stat"]:
        return hw.Delta(sub_static=v) if static else hw.Delta(sub=v)
    return hw.Delta()


def text_delta(text: str, job: dict, static: bool = False) -> hw.Delta:
    """'보스 몬스터 공격 시 데미지 20% 증가', '힘 150 증가', 'STR 16 증가' 같은 문장 1개."""
    t = text.strip()
    att_word = "공격력" if job["attack"] == "ATT" else "마력"
    if m := re.fullmatch(r"(힘|민첩성|지능|운) (\d+) 증가", t):
        return _stat(job, STAT_WORD[m.group(1)], float(m.group(2)), static)
    if m := re.fullmatch(r"(STR|DEX|INT|LUK) (\d+) 증가", t):
        return _stat(job, m.group(1), float(m.group(2)), static)
    if m := re.fullmatch(r"모든 능력치 (\d+) 증가", t):
        v = float(m.group(1))
        return _stat(job, job["main_stat"], v, static) + _stat(job, job["sub_stat"], v, static)
    if m := re.fullmatch(r"공격력과 마력 (\d+) 증가", t):
        return hw.Delta(att=float(m.group(1)))
    if m := re.fullmatch(rf"{att_word} (\d+) 증가", t):
        return hw.Delta(att=float(m.group(1)))
    if m := re.fullmatch(r"보스 몬스터 공격 시 데미지 (\d+)% 증가", t):
        return hw.Delta(boss=float(m.group(1)))
    if m := re.fullmatch(r"데미지 (\d+)% 증가", t):
        return hw.Delta(dmg=float(m.group(1)))
    if m := re.fullmatch(r"크리티컬 확률 (\d+)% 증가", t):
        return hw.Delta(crit_rate=float(m.group(1)))
    if m := re.fullmatch(r"크리티컬 데미지 (\d+)% 증가", t):
        return hw.Delta(crit_dmg=float(m.group(1)))
    if m := re.fullmatch(r"(?:몬스터 )?방어율 무시 (\d+)% 증가", t):
        return hw.Delta(ied=float(m.group(1)))
    return hw.Delta()


def ability_lines(ability: dict, p: int) -> list[str]:
    preset = ability.get(f"ability_preset_{p}") or {}
    return [a["ability_value"] for a in preset.get("ability_info") or []]


def ability_delta(ability: dict, p: int, job: dict) -> hw.Delta:
    total = hw.Delta()
    for line in ability_lines(ability, p):
        for part in line.split(", "):  # 'DEX 20 증가, INT 10 증가'
            total = total + text_delta(part, job)
    return total


def hyper_rows(hyper: dict, p: int) -> list[dict]:
    return [r for r in hyper.get(f"hyper_stat_preset_{p}") or [] if r.get("stat_level")]


def hyper_delta(hyper: dict, p: int, job: dict) -> hw.Delta:
    total = hw.Delta()
    for r in hyper_rows(hyper, p):
        if r.get("stat_increase"):
            total = total + text_delta(r["stat_increase"], job, static=True)  # 하이퍼 스탯은 미적용
    return total


# ---------------------------------------------------------------- 현재 / 자동 추정


def current_presets(equip: dict, ability: dict, hyper: dict) -> dict:
    return {
        "equipment": int(equip.get("preset_no") or 1),
        "ability": int(ability.get("preset_no") or 1),
        "hyper": int(hyper.get("use_preset_no") or 1),
    }


def preset_items_raw(equip: dict, p: int) -> list[dict]:
    if p == int(equip.get("preset_no") or 0):
        return equip["item_equipment"]
    return equip.get(f"item_equipment_preset_{p}") or equip["item_equipment"]


def _farm_lines(items: list[dict]) -> int:
    n = 0
    for it in items:
        for pre in ("potential_option", "additional_potential_option"):
            for i in (1, 2, 3):
                if any(w in (it.get(f"{pre}_{i}") or "") for w in FARM_WORDS):
                    n += 1
    return n


def _pick(scores: dict[int, float], current: int, highest: bool, keep_current: bool = False) -> int:
    """최고(또는 최저) 점수 프리셋. 동점이면 현재 → 낮은 번호 순.
    keep_current: 현재 프리셋 점수가 0보다 크면 그대로 (재획 프리셋이 여럿인 경우 지금 쓰는 것)"""
    if keep_current and scores.get(current, 0) > 0:
        return current
    best = max(scores.values()) if highest else min(scores.values())
    tied = [p for p, s in scores.items() if s == best]
    return current if current in tied else min(tied)


def guess(equip: dict, ability: dict, hyper: dict) -> dict:
    """보스용 / 재획용 프리셋 자동 추정."""
    cur = current_presets(equip, ability, hyper)
    eq = {p: _farm_lines(preset_items_raw(equip, p)) for p in (1, 2, 3)}
    ab_farm = {p: sum(any(w in ln for w in FARM_WORDS) for ln in ability_lines(ability, p)) for p in (1, 2, 3)}
    ab_boss = {p: sum(float(m.group(1)) for ln in ability_lines(ability, p)
                      if (m := re.search(r"보스 몬스터 공격 시 데미지 (\d+)%", ln))) for p in (1, 2, 3)}

    def hy(p: int, words: tuple[str, ...]) -> float:
        return sum(r["stat_level"] for r in hyper_rows(hyper, p) if any(w in r["stat_type"] for w in words))

    hy_boss = {p: hy(p, ("보스 몬스터", "방어율 무시", "공격력/마력", "STR", "DEX", "INT", "LUK")) for p in (1, 2, 3)}
    hy_farm = {p: hy(p, ("일반 몬스터", "획득 경험치", "아케인포스")) for p in (1, 2, 3)}
    return {
        "boss": {"equipment": _pick(eq, cur["equipment"], False), "ability": _pick(ab_boss, cur["ability"], True),
                 "hyper": _pick(hy_boss, cur["hyper"], True)},
        "farming": {"equipment": _pick(eq, cur["equipment"], True, True),
                    "ability": _pick(ab_farm, cur["ability"], True, True),
                    "hyper": _pick(hy_farm, cur["hyper"], True, True)},
    }


# ---------------------------------------------------------------- 세트


def mapped_counts(names: list[str], members: dict[str, list[str]]) -> dict[str, int]:
    out = {k: 0 for k in members}
    for n in names:
        for k in gear.item_sets(n, members):
            out[k] += 1
    return out


def view_sets(api_sets: list[dict], cur_names: list[str], new_names: list[str],
              members: dict[str, list[str]]) -> list[dict]:
    """대상 프리셋의 세트 목록 (API 세트 수 + 매핑 차이). 럭키 아이템 보정은 API 수에 포함된 그대로 유지."""
    cur, new = mapped_counts(cur_names, members), mapped_counts(new_names, members)
    catalog = load_set_catalog()
    out = [s for s in api_sets if not any(k in s["set_name"] for k in members)]
    for k in members:
        api = next((s for s in api_sets if k in s["set_name"]), None)
        count = (api["total_set_count"] if api else 0) + new[k] - cur[k]
        if count <= 0:
            continue
        name = api["set_name"] if api else next((n for n in catalog if k in n), k)
        full = (api or {}).get("set_option_full") or catalog.get(name, [])
        out.append({"set_name": name, "total_set_count": count, "set_option_full": full,
                    "missing_options": not full})
    return out


def sets_total(sets: list[dict], members: dict[str, list[str]], job: dict, level: int) -> hw.Delta:
    """매핑된 세트의 활성 효과 합."""
    total = hw.Delta()
    for s in sets:
        if any(k in s["set_name"] for k in members):
            total = total + gear.set_bonus(s.get("set_option_full") or [], s["total_set_count"], job, level)
    return total
