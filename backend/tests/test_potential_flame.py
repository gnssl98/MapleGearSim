import pytest

from app.engine.flame import (
    ScoreCoef,
    prob_score_at_least,
    score_distribution,
    weapon_attack_value,
    weapon_probability,
)
from app.engine.potential import Condition as C
from app.engine.potential import calculate, grade_stages, option_probability, parse_option, presets


@pytest.mark.parametrize(
    "text,expected",
    [
        ("STR +13%", ("STR%", 13)),
        ("올스탯 +10%", ("ALL%", 10)),
        ("공격력 +32", ("ATT", 32)),
        ("보스 몬스터 데미지 +40%", ("BOSS%", 40)),
        ("스킬 재사용 대기시간 -2초", ("CDR", 2)),
        ("캐릭터 기준 9레벨 당 LUK +2", ("LUK/9LV", 2)),
        ("크리티컬 데미지 +8%", ("CRIT_DMG", 8)),
    ],
)
def test_parse_option(text, expected):
    assert parse_option(text) == expected


@pytest.mark.parametrize(
    "kind,part,conds,expected_pct",
    [
        # 리서치 04 §6.2 — 공식 확률표 직접 계산값, begchi 계산기와 교차 검증됨
        ("potential", "weapon", [C(["ATT%", "BOSS%"], 3, "count")], 0.4183),
        ("potential", "emblem", [C(["ATT%"], 3, "count")], 0.0302),
        ("potential", "top", [C(["STR%", "ALL%"], 33)], 0.0230),
        ("potential", "top", [C(["STR%", "ALL%"], 30)], 0.1204),
        ("potential", "gloves", [C(["CRIT_DMG"], 2, "count")], 0.2584),
        ("potential", "hat", [C(["CDR"], 2)], 6.18),
        ("potential", "ring", [C(["MESO%", "DROP%"], 2, "count")], 0.6081),
        ("additional", "weapon", [C(["ATT%"], 2, "count")], 0.6716),
    ],
)
def test_option_probability_matches_research(kind, part, conds, expected_pct):
    assert option_probability(kind, part, 200, conds) * 100 == pytest.approx(expected_pct, rel=0.005)


def test_grade_up_expected_attempts_with_pity():
    stages = grade_stages("potential", 200, "rare", "legendary")
    assert [round(s.expected_attempts, 1) for s in stages] == [5.4, 22.2, 55.6]


def test_pity_used_reduces_expectation():
    fresh = grade_stages("potential", 200, "unique", "legendary")[0]
    used = grade_stages("potential", 200, "unique", "legendary", pity_used={"unique": 100})[0]
    assert used.expected_attempts < fresh.expected_attempts
    assert used.pity == 7


def test_calculate_unique_to_legendary_meso():
    # 200제 유→레 ≈ 55.6 × 3,825만 ≈ 21.3억 (리서치 04 §6.1)
    r = calculate("potential", "top", 200, "unique", seed=1, trials=50_000)
    assert r.grade_up_expected_meso / 1e8 == pytest.approx(21.3, rel=0.01)
    assert r.percentiles["p50"] <= r.percentiles["p90"]


def test_presets_for_adele_top():
    ids = [p["id"] for p in presets("adele", "top", "potential", 250)]
    assert "main33" in ids and "main36" in ids


@pytest.mark.parametrize("threshold,expected_pct", [(100, 6.59), (120, 2.29), (140, 0.62), (160, 0.105)])
def test_flame_score_matches_research(threshold, expected_pct):
    # 리서치 04 §4.4: 200제 보스 방어구, LUK 직업, 부스탯 무시, 검은 환불(=메소 재설정)
    dist = score_distribution(200, True, "meso_reset", "LUK", "DEX", "ATT", ScoreCoef(sub=0))
    assert prob_score_at_least(dist, threshold) * 100 == pytest.approx(expected_pct, rel=0.01)


def test_flame_distribution_sums_to_one():
    dist = score_distribution(160, False, "burning", "STR", "DEX")
    assert sum(dist.values()) == pytest.approx(1.0)


def test_weapon_flame_att_tier():
    # 보스 무기 4옵, 공격력 선택 4/19 × 단계 ≥6 (원래 4~5단계: 0.25+0.01)
    assert weapon_probability(True, "meso_reset", {"ATT": 6}) == pytest.approx(4 / 19 * 0.26)


def test_weapon_attack_flame_matches_ingame():
    # 리서치 09: 아케인셰이드 투핸드소드(기본 295) 3~7단계 54/78/108/142/182, 제네시스(340) 1추 210
    assert [weapon_attack_value(295, 200, t, True) for t in range(3, 8)] == [54, 78, 108, 142, 182]
    assert weapon_attack_value(340, 200, 7, True) == 210


def test_eternel_single_stat_is_12_per_tier():
    from app.engine.flame import _option_score_per_tier
    assert _option_score_per_tier("STR", 250, True, "STR", "DEX", "ATT", ScoreCoef()) == 12
