"""오픈 API 응답 파서 테스트 (응답 구조만 모사한 가짜 데이터)."""

import pytest

from app.engine import flame as fl
from app.engine.potential import load_jobs
from app.nexon.character import is_boss_flame_item, job_for_class, parse_item, stat_attack_check

ADELE = load_jobs()["jobs"]["adele"]


def _item(**over):
    base = {
        "item_equipment_slot": "모자",
        "item_name": "에테르넬 나이트헬름",
        "item_icon": None,
        "item_base_option": {"attack_power": "10", "base_equipment_level": 250},
        "item_add_option": {"str": "71", "int": "35", "attack_power": "5", "all_stat": "5", "dex": "0"},
        "potential_option_grade": "레전드리",
        "potential_option_1": "STR +13%",
        "potential_option_2": "STR +10%",
        "potential_option_3": "올스탯 +7%",
        "additional_potential_option_grade": "에픽",
        "additional_potential_option_1": "STR +5%",
        "additional_potential_option_2": None,
        "additional_potential_option_3": None,
        "starforce": "22",
        "starforce_scroll_flag": "미사용",
        "cuttable_count": "10",
        "scroll_upgrade": "12",
        "item_total_option": {},
    }
    base.update(over)
    return base


def test_parse_armor_item():
    it = parse_item(_item(), ADELE, fl.ScoreCoef())
    assert it["part"] == "hat" and it["level"] == 250 and it["starforce"] == 22
    assert it["boss_flame"] is True
    assert it["potential_grade"] == "legendary"
    assert [p["key"] for p in it["potential"]] == ["STR%", "STR%", "ALL%"]
    assert len(it["additional"]) == 1
    # STR 71 + 공 5×4 + 올% 5×10 = 141
    assert it["flame_score"] == pytest.approx(141)


def test_weapon_flame_rank_genesis():
    it = parse_item(_item(
        item_equipment_slot="무기", item_name="제네시스 튜너",
        item_base_option={"attack_power": "340", "base_equipment_level": 200},
        item_add_option={"attack_power": "210"},
    ), ADELE, fl.ScoreCoef())
    assert it["part"] == "weapon"
    assert it["weapon_flame_rank"] == 1
    assert it["flame_score"] is None


def test_boss_detection():
    assert is_boss_flame_item("아케인셰이드 나이트글러브")
    assert is_boss_flame_item("몽환의 벨트")
    assert not is_boss_flame_item("하프 이어링")
    assert not is_boss_flame_item("영생의 돌")


def test_challenger_gear_not_craftable():
    it = parse_item(_item(item_name="도전자의 모자"), ADELE, fl.ScoreCoef())
    assert it["craftable"] is False


def test_class_map():
    assert job_for_class("아델") == "adele"
    assert job_for_class("렌") == "ren"
    assert job_for_class("비숍") is None


def test_stat_attack_check():
    stats = {"STR": "50000", "DEX": "7000", "공격력": "6600", "데미지": "100.00", "최종 데미지": "80.00"}
    expected = 1.3 * (4 * 50000 + 7000) * 0.01 * 6600 * 2.0 * 1.8
    stats["최대 스탯공격력"] = str(expected)
    assert stat_attack_check(stats, ADELE)["error_pct"] == pytest.approx(0, abs=1e-9)
