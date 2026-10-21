"""시세 추정(기록된 매물) / 매물 vs 직작 비교 / 되팔기 / 노작+직작 후보 테스트."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import store
from app.engine import compare as cmp
from app.engine import hwansan as hw
from app.engine import market as mk
from app.engine import recommend as rc
from app.engine.potential import load_jobs
from app.main import app

ADELE = load_jobs()["jobs"]["adele"]
client = TestClient(app)
NOW = datetime(2026, 10, 16, 12, 0)


def _row(id, star, price, grade="legendary", world="own", when="2026-10-15T10:00", **kw):
    return {"id": id, "observed_at": when, "item_name": "에테르넬 나이트헬름", "slot": "hat", "item_level": "250",
            "star": str(star), "potential_grade": grade, "price_meso": str(price), "world_type": world, **kw}


ROWS = [
    _row("base1", 0, 8e9, grade=""),
    _row("base2", 0, 10e9, grade="", world="other"),     # 실구매 11e9
    _row("f1", 22, 50e9), _row("f2", 21, 40e9), _row("f3", 18, 20e9),
    _row("old", 22, 99e9, when="2026-01-01T10:00"),       # 30일 밖
]


def test_estimate_finished_recent_and_star_tolerance():
    est = mk.estimate(mk.match(ROWS, "에테르넬 나이트헬름", star=22, grade="legendary"), now=NOW)
    assert est.n == 2 and est.recent_only            # f1, f2 (old 는 최근 30일 밖이라 제외)
    assert est.price == pytest.approx(45e9)


def test_estimate_base_uses_effective_price():
    est = mk.estimate(mk.match(ROWS, "에테르넬 나이트헬름", base=True), now=NOW)
    assert est.n == 2 and est.price == pytest.approx((8e9 + 11e9) / 2)


def test_resale_net_of_fee_and_untradeable():
    item = {"name": "에테르넬 나이트헬름", "starforce": 18, "potential_grade": "legendary", "cuttable_count": 5}
    net, est, why = mk.resale(ROWS, item, 0.05)
    assert why is None and net == pytest.approx(20e9 * 0.95)
    assert mk.resale(ROWS, {**item, "cuttable_count": 0}, 0.05)[0] == 0


def test_conditions_from_listing_lines():
    conds = mk.conditions_from_lines([("STR%", 13), ("ALL%", 10), ("BOSS%", 30)], ADELE)
    assert conds[0].keys == ["ALL%", "STR%"] and conds[0].min == 23
    assert conds[1].keys == ["BOSS%"] and conds[1].mode == "count" and conds[1].min == 1


def test_compare_with_resale():
    import numpy as np
    st = cmp.StageCost("x", 10e9, np.full(1000, 10e9))
    r = cmp.compare([st], 0, 30e9, resale_net=25e9)
    assert r.market_net == pytest.approx(5e9)
    assert r.expected_profit == pytest.approx(-5e9)   # 직작 10억 > 구매 실비용 5억
    assert r.loss_probability == 1.0


@pytest.fixture
def user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(store, "LISTINGS_PATH", tmp_path / "listings.csv")


def test_craft_compare_endpoint(user_data):
    base = store.add_listing({"item_name": "에테르넬 나이트헬름", "slot": "hat", "item_level": 250, "star": 0,
                              "price_meso": 9e9, "world_type": "own"})
    target = store.add_listing({"item_name": "에테르넬 나이트헬름", "slot": "hat", "item_level": 250, "star": 18,
                                "potential_grade": "legendary", "pot1": "STR +13%", "pot2": "STR +10%",
                                "flame_score": 130, "price_meso": 60e9, "world_type": "other"})
    r = client.post("/api/market/craft-compare", json={"listing_id": target["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    c = body["compare"]
    assert c["base_price"] == pytest.approx(9e9)
    assert c["market_price"] == pytest.approx(66e9)
    assert c["breakeven_price"] == pytest.approx(c["base_price"] + c["craft_expected"])
    assert {s["name"] for s in c["cumulative_breakeven"]} == {"스타포스", "잠재능력", "추가옵션"}
    assert body["target"]["potential"]["conditions"][0]["min"] == 23
    assert base["id"] != target["id"]

    r = client.get("/api/market/estimate", params={"item_name": "에테르넬 나이트헬름", "base": True})
    assert r.json()["price"] == pytest.approx(9e9)


def test_base_candidates_and_resale_in_buy():
    spec = hw.Spec(main=50000, sub=7000, main_pct=330, sub_pct=100, main_static=23000, sub_static=0, att=6600,
                   att_pct=100, dmg=100, boss=300, final_dmg=80, ied=90, crit_rate=100, crit_dmg=90)
    ctx = rc.Context(spec=spec, a=hw.Assumptions(), job_id="adele", job=ADELE, char_level=286)
    cur = {"slot": "모자", "part": "hat", "name": "에테르넬 나이트헬름", "level": 250, "starforce": 18,
           "starforce_scroll": False, "craftable": True, "potential_grade": "legendary",
           "potential": [{"key": "STR%", "value": 10}], "additional_grade": None, "additional": [],
           "boss_flame": True, "flame_score": 120, "weapon_flame_rank": None, "weapon_base_att": 0,
           "hwansan": 5000, "cuttable_count": 5}
    rows = [_row("b", 0, 8e9, grade=""), _row("f", 18, 20e9, pot1="STR +13%", pot2="STR +10%", pot3="STR +10%"),
            _row("g", 19, 30e9, pot1="STR +13%", pot2="STR +13%", pot3="STR +10%")]
    base = rc.base_candidates(ctx, [cur], rows, {})
    assert base and all(c.kind == "base" for c in base)
    assert any("22성" in c.label for c in base)
    buy = [c for c in rc.buy_candidates(ctx, [cur], rows) if c.label == "매물 에테르넬 나이트헬름 19성"]
    # 내 18성 레전 모자의 비슷한 매물(f 20억, g 30억 → 중앙값 25억) × 0.95 를 되팔기로 차감
    assert buy[0].cost == pytest.approx(30e9 - 25e9 * 0.95)
    plan = rc.optimize_budget(base + buy, 100e9)
    assert sum(1 for c in plan["chosen"] if c["slot"] == "모자") == 1  # 구매류는 슬롯당 하나
