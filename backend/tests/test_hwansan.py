"""환산 엔진 / 스타포스 스탯 / 세트 / 추천 테스트."""

import math

import pytest

from app.engine import flame as fl
from app.engine import gear
from app.engine import hwansan as hw
from app.engine import recommend as rc
from app.engine.potential import load_jobs

ADELE = load_jobs()["jobs"]["adele"]
A = hw.Assumptions()


def _spec(**over):
    base = dict(main=50000, sub=7000, main_pct=330, sub_pct=100, main_static=23000, sub_static=0,
                att=6600, att_pct=100, dmg=100, boss=300, final_dmg=80, ied=90, crit_rate=100, crit_dmg=90)
    base.update(over)
    return hw.Spec(**base)


def test_unit_is_one():
    spec = _spec()
    assert hw.hwansan(spec, hw.Delta(main_static=1), A) == pytest.approx(1)


def test_pct_equals_pure_stat():
    spec = _spec()
    # 주스탯 1% ≈ 순수 주스탯 × 1% 만큼의 최종 주스탯
    assert hw.hwansan(spec, hw.Delta(main_pct=1), A) == pytest.approx(spec.main_pure * 0.01, rel=1e-3)


def test_apply_roundtrip_multiplicative():
    spec = _spec()
    d = hw.Delta(main=100, main_pct=9, att=30, ied=30, final_dmg=10, boss=12)
    back = hw.apply(hw.apply(spec, d), d, -1)
    for k in ("main", "att", "ied", "final_dmg", "boss"):
        assert getattr(back, k) == pytest.approx(getattr(spec, k))
    # 방무는 곱연산: 90% + 30% → 93%
    assert hw.apply(spec, hw.Delta(ied=30)).ied == pytest.approx(93)


def test_remove_then_gain_consistent():
    spec = _spec()
    d = hw.Delta(main=300, att=50)
    lost = hw.hwansan(spec, d, A, sign=-1)
    regained = hw.hwansan(hw.apply(spec, d, -1), d, A)
    assert lost == pytest.approx(regained * hw.unit_log(hw.apply(spec, d, -1), A) / hw.unit_log(spec, A))


@pytest.mark.parametrize("part,level,star,base_att,expected", [
    ("hat", 250, 22, 0, (159, 120)),       # 에테르넬 나이트헬름 (API 실측)
    ("gloves", 200, 18, 0, (85, 46)),      # 아케인셰이드 장갑: 1~15성 공 +7
    ("ring", 140, 22, 0, (103, 78)),       # 마이스터링
    ("heart", 130, 20, 0, (75, 45)),       # 플라즈마 하트
    ("earring", 75, 5, 0, (10, 0)),
    ("weapon", 200, 22, 412, (145, 253)),  # 제네시스 무기 (기본 340 + 주문서 72)
])
def test_star_bonus_matches_api(part, level, star, base_att, expected):
    assert hw.star_bonus(part, level, star, base_att) == expected


def test_star_delta_250_weapon_unknown_range():
    assert hw.star_delta("weapon", 250, 22, 23) is None


def test_set_option_parse_and_loss():
    d = gear.parse_set_option("올스탯  +10, 최대 HP  +250, 공격력  +10, 마력  +10, 보스 몬스터 데미지 +10%", ADELE, 280)
    assert (d.main, d.sub, d.att, d.boss) == (10, 10, 10, 10)
    sets = [{"set_name": "여명의 보스 세트", "total_set_count": 2, "set_option_full": [
        {"set_count": 2, "set_option": "올스탯  +10, 공격력  +10, 보스 몬스터 데미지 +10%"},
        {"set_count": 4, "set_option": "몬스터 방어율 무시 +10%"},
    ]}]
    members = {"여명의 보스 세트": ["트와일라이트 마크"]}
    loss = gear.set_loss("트와일라이트 마크", sets, members, ADELE, 280)
    assert (loss.main, loss.att, loss.boss) == (10, 10, 10)
    assert gear.set_loss("하프 이어링", sets, members, ADELE, 280).att == 0


def test_line_delta_level_scaling():
    assert gear.line_delta("STR/9LV", 2, ADELE, 286).main == 2 * 31


def _ctx():
    return rc.Context(spec=_spec(), a=A, job_id="adele", job=ADELE, char_level=286)


def _item(**over):
    it = {"slot": "모자", "part": "hat", "name": "에테르넬 나이트헬름", "level": 250, "starforce": 18,
          "starforce_scroll": False, "craftable": True, "potential_grade": "legendary",
          "potential": [{"key": "STR%", "value": 10}, {"key": "STR%", "value": 10}],
          "additional_grade": None, "additional": [], "boss_flame": True, "flame_score": 120,
          "weapon_flame_rank": None, "weapon_base_att": 0, "hwansan": 10000}
    it.update(over)
    return it


def test_starforce_candidates():
    cands = rc.starforce_candidates(_ctx(), _item())
    assert [c.label for c in cands] == ["18→19성", "18→20성", "18→21성", "18→22성"]
    assert all(c.gain > 0 and c.cost > 0 for c in cands)
    assert cands[0].gain < cands[-1].gain
    assert "event_cost" in cands[0].detail and cands[0].detail["event_cost"] < cands[0].cost


def test_starforce_skips_genesis_and_scroll():
    assert rc.starforce_candidates(_ctx(), _item(name="제네시스 튜너", part="weapon")) == []
    assert rc.starforce_candidates(_ctx(), _item(starforce_scroll=True)) == []


def test_potential_candidates_improve_only():
    cands = rc.potential_candidates(_ctx(), _item(), "potential")
    assert cands and all(c.gain > 0 for c in cands)
    labels = [c.label for c in cands]
    assert "주스탯 24%+" in labels and "주스탯 33%+" in labels  # 250제는 +1%p 씩: 24 = 21+3
    # 이미 33%면 그 이하 목표는 후보에서 빠짐
    better = _item(potential=[{"key": "STR%", "value": 13}] * 3)
    assert all(c.label in ("주스탯 36%+",) for c in rc.potential_candidates(_ctx(), better, "potential"))


def test_flame_candidates():
    cands = rc.flame_candidates(_ctx(), _item(), {})
    assert 0 < len(cands) <= 3
    assert all(c.detail["target"] > 120 for c in cands)


def test_buy_candidate_mixed_strategy():
    listing = {"id": "x", "slot": "hat", "item_name": "에테르넬 나이트헬름", "item_level": "250", "star": "17",
               "pot1": "STR +13%", "pot2": "STR +10%", "pot3": "STR +10%", "flame_score": "150",
               "price_meso": "3000000000", "world_type": "other"}
    cands = rc.buy_candidates(_ctx(), [_item()], [listing])
    assert cands[0].cost == pytest.approx(3.3e9)  # 타서버 +10%
    assert cands[0].gain > 0
    assert any("+ 17→" in c.label for c in cands[1:])


def test_optimize_budget_knapsack():
    def c(slot, kind, gain, cost):
        return rc.Candidate(slot, slot, kind, f"{kind}{gain}", gain, 0, cost)

    cands = [
        c("a", "starforce", 100, 5e8), c("a", "starforce", 150, 9e8), c("a", "potential", 80, 4e8),
        c("b", "starforce", 120, 6e8), c("b", "buy", 300, 10e8),
    ]
    plan = rc.optimize_budget(cands, 10e8)
    # 10억: a 스타포스100(5) + a 잠재80(4) = 180 (9억) vs b 구매 300 (10억) → 300
    assert plan["gain"] == pytest.approx(300)
    plan = rc.optimize_budget(cands, 15e8)
    # 15억: b구매 300(10) + a 스타포스 100(5) = 400
    assert plan["gain"] == pytest.approx(400)
    assert math.isclose(plan["cost"], 15e8)


def test_flame_score_default_coef_matches_settings():
    assert fl.ScoreCoef().main == 1
