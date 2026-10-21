"""보스용/재획용 프리셋 추정 테스트 (오픈 API 구조 모사)."""

import pytest

from app.engine.potential import load_jobs
from app.nexon import presets as pr

ADELE = load_jobs()["jobs"]["adele"]


def test_text_delta():
    assert pr.text_delta("보스 몬스터 공격 시 데미지 20% 증가", ADELE).boss == 20
    assert pr.text_delta("힘 150 증가", ADELE, static=True).main_static == 150
    assert pr.text_delta("민첩성 90 증가", ADELE, static=True).sub_static == 90
    assert pr.text_delta("공격력과 마력 18 증가", ADELE).att == 18
    assert pr.text_delta("방어율 무시 27% 증가", ADELE).ied == 27
    assert pr.text_delta("모든 능력치 15 증가", ADELE).main == 15
    assert pr.text_delta("아이템 드롭률 20% 증가", ADELE).boss == 0


def _item(slot, name, pot=("STR +9%",)):
    return {"item_equipment_slot": slot, "item_name": name,
            **{f"potential_option_{i + 1}": p for i, p in enumerate(pot)}}


def _equip():
    boss = [_item("귀고리", "에스텔라 이어링"), _item("얼굴장식", "트와일라이트 마크")]
    farm = [_item("귀고리", "하프 이어링", ("메소 획득량 +20%", "아이템 드롭률 +20%")),
            _item("얼굴장식", "레드 워리어 마이스터 심볼", ("메소 획득량 +20%",))]
    return {"preset_no": 2, "item_equipment": farm,
            "item_equipment_preset_1": boss, "item_equipment_preset_2": farm, "item_equipment_preset_3": boss}


ABILITY = {"preset_no": 2,
           "ability_preset_1": {"ability_info": [{"ability_value": "보스 몬스터 공격 시 데미지 20% 증가"}]},
           "ability_preset_2": {"ability_info": [{"ability_value": "아이템 드롭률 20% 증가"}]},
           "ability_preset_3": {"ability_info": [{"ability_value": "보스 몬스터 공격 시 데미지 10% 증가"}]}}


def _hy(stat_type, level, text):
    return {"stat_type": stat_type, "stat_level": level, "stat_increase": text}


HYPER = {"use_preset_no": 2,
         "hyper_stat_preset_1": [_hy("보스 몬스터 공격 시 데미지 증가", 15, "보스 몬스터 공격 시 데미지 55% 증가")],
         "hyper_stat_preset_2": [_hy("일반 몬스터 공격 시 데미지 증가", 15, "일반 몬스터 공격 시 데미지 55% 증가")],
         "hyper_stat_preset_3": []}


def test_guess_boss_and_farming():
    g = pr.guess(_equip(), ABILITY, HYPER)
    assert g["boss"] == {"equipment": 1, "ability": 1, "hyper": 1}
    assert g["farming"] == {"equipment": 2, "ability": 2, "hyper": 2}


def test_hyper_ability_delta():
    assert pr.hyper_delta(HYPER, 1, ADELE).boss == 55
    assert pr.ability_delta(ABILITY, 3, ADELE).boss == 10


def test_view_sets_adds_missing_set_from_catalog():
    members = {"여명의 보스 세트": ["에스텔라 이어링", "트와일라이트 마크"], "마이스터 세트": ["마이스터"]}
    api_sets = [{"set_name": "마이스터 세트", "total_set_count": 1, "set_option_full": []}]
    out = pr.view_sets(api_sets, ["레드 워리어 마이스터 심볼"], ["에스텔라 이어링", "트와일라이트 마크"], members)
    names = {s["set_name"]: s["total_set_count"] for s in out}
    assert names == {"여명의 보스 세트": 2}
    dawn = next(s for s in out if s["set_name"] == "여명의 보스 세트")
    assert dawn["set_option_full"]  # sets.yaml 카탈로그에서 채움
    total = pr.sets_total(out, members, ADELE, 286)
    assert total.boss == pytest.approx(10) and total.att == 10
