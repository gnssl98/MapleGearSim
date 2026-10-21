"""구매 상한가: 직작 비용 vs 효율 기준가, 되팔기, 쿨감 모자 보호."""

import pytest

from app.engine import hwansan as hw
from app.engine import recommend as rc
from app.engine import shopping as sh
from app.engine.potential import load_jobs

ADELE = load_jobs()["jobs"]["adele"]
SPEC = hw.Spec(main=50000, sub=7000, main_pct=330, sub_pct=100, main_static=23000, sub_static=0, att=6600,
               att_pct=100, dmg=100, boss=300, final_dmg=80, ied=90, crit_rate=100, crit_dmg=90)
CTX = rc.Context(spec=SPEC, a=hw.Assumptions(), job_id="adele", job=ADELE, char_level=286)


def _item(pot, star=18, part="top", name="에테르넬 나이트아머", slot="상의", grade="legendary"):
    return {"slot": slot, "part": part, "name": name, "level": 250, "starforce": star, "starforce_scroll": False,
            "craftable": True, "potential_grade": grade, "potential": pot, "additional_grade": None,
            "additional": [], "boss_flame": True, "flame_score": 120, "weapon_flame_rank": None,
            "weapon_base_att": 0, "hwansan": 5000, "cuttable_count": 5}


STR = [{"text": "STR +13%", "key": "STR%", "value": 13}, {"text": "STR +10%", "key": "STR%", "value": 10}]


def test_cap_is_min_of_craft_and_value_plus_resale():
    rows = sh.targets_for_item(CTX, _item(STR), [], threshold=20)
    assert rows and all(r.gain > 1 for r in rows)
    for r in rows:
        assert r.cap == pytest.approx(min(r.craft_cost, r.gain / 20 * 1e8) + r.resale)
        assert r.binding == ("value" if r.value_cap < r.craft_cost else "craft")
    star22 = next(r for r in rows if r.star == 22 and "현재" in r.potential)
    assert "22성 이상" in star22.search and "추옵 120급 이상" in star22.search


def test_threshold_off_uses_craft_cost_only():
    rows = sh.targets_for_item(CTX, _item(STR), [], threshold=0)
    assert all(r.value_cap is None and r.binding == "craft" and r.cap == pytest.approx(r.craft_cost) for r in rows)


def test_resale_from_listings():
    listing = {"id": "x", "observed_at": "2099-01-01T00:00", "item_name": "에테르넬 나이트아머", "slot": "top",
               "star": "18", "potential_grade": "legendary", "price_meso": str(20e9), "world_type": "own"}
    rows = sh.targets_for_item(CTX, _item(STR), [listing], threshold=None)
    assert rows[0].resale == pytest.approx(20e9 * 0.95)
    assert rows[0].cap == pytest.approx(rows[0].craft_cost + rows[0].resale)


def test_cdr_hat_keeps_cdr_targets_and_no_potential_item():
    cdr = [{"text": "스킬 재사용 대기시간 -2초", "key": "CDR", "value": 2}] * 2
    hat = _item(cdr, part="hat", name="에테르넬 나이트헬름", slot="모자", star=22)
    rows = sh.targets_for_item(CTX, hat, [], threshold=20)
    assert rows and all("주스탯" not in r.potential for r in rows)
    ring = _item([], part="ring", name="리스트레인트 링", slot="반지1", star=0, grade=None)
    assert sh.targets_for_item(CTX, ring, [], threshold=20) == []


def test_threshold_from_plan_ignores_free_items():
    plan = {"chosen": [{"per_eok": 40, "cost": 1e9}, {"per_eok": 25, "cost": 2e9}, {"per_eok": 1e12, "cost": -1}]}
    assert sh.threshold_from_plan(plan) == 25
    assert sh.threshold_from_plan({"chosen": []}) is None


def test_next_step_targets_cap_is_base_plus_craft():
    it = {**_item(STR, part="pendant", name="도미네이터 펜던트", slot="펜던트"), "level": 140, "next_steps": [{"tier": "칠흑", "name": "고통의 근원", "label": "고통의 근원", "level": 160,
                                     "part": "pendant", "id": 1122430}]}
    listings = [{"id": "b", "observed_at": "2099-01-01T00:00", "item_name": "고통의 근원", "slot": "pendant",
                 "star": "0", "potential_grade": "", "price_meso": str(30e8), "world_type": "own"}]
    rows = sh.next_targets(CTX, it, listings)
    assert rows and all(r.kind == "next" and r.resale == 0 for r in rows)
    assert {r.star for r in rows} >= {17, 22}
    for r in rows:
        assert r.cap == pytest.approx(r.craft_cost + r.base_price)
    assert rows[0].icon == "/api/icon/1122430"
