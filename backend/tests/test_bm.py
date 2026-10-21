"""확률형 BM 기댓값·손익분기, MVP 작 비교."""

import pytest

from app.engine import bm
from app.engine import mvp as mv

ROWS = [{"item": "대박", "prob": 0.01}, {"item": "중박", "prob": 0.09}, {"item": "꽝", "prob": 0.9}]


def test_ev_and_breakeven():
    # 1회 1,000원 · 100,000원 → 100회. 1억 = 2,000원 → 현질 50억 메소
    vals = {"대박": 100e8, "중박": 10e8, "꽝": 0}
    r = bm.evaluate(ROWS, vals, {"대박"}, 1000, 100_000, 2000, fee=0.05, trials=4000)
    assert r.pulls == 100 and r.spend_meso == pytest.approx(50e8)
    assert r.ev_per_pull == pytest.approx((0.01 * 100e8 + 0.09 * 10e8) * 0.95)
    assert r.recovery == pytest.approx(r.expected / 50e8)
    # 당첨 외 기대 = 100 × 0.09 × 9.5억 = 85.5억 → 이미 본전 이상이라 당첨 0개면 됨
    assert r.need == 0 and r.need_prob == 1.0
    r2 = bm.evaluate(ROWS, {"대박": 100e8}, {"대박"}, 1000, 100_000, 2000, fee=0.05, trials=4000)
    assert r2.need == 1  # 95억 × 1개 ≥ 50억
    assert r2.need_prob == pytest.approx(1 - 0.99 ** 100, rel=1e-6)
    assert 0.55 < r2.profit_prob < 0.7
    assert r2.breakeven_price_won == pytest.approx(r2.ev_per_pull / 1e8 * 2000)


def test_binom_helpers():
    assert bm.binom_tail(10, 0.5, 0) == 1.0
    assert bm.binom_tail(10, 0.5, 11) == 0.0
    assert sum(bm.binom_pmf(20, 0.3, 20)) == pytest.approx(1.0)


def test_loaded_tables_sum_to_one():
    t = bm.load_tables()
    assert t["products"]
    for p in t["products"]:
        for tb in p["tables"]:
            assert abs(tb["total"] - 1) <= 0.02, (p["name"], tb["title"])


def test_mvp_compare_orders_by_net_cost():
    out = mv.compare(current_cash=100_000, target="silver", sf_meso=100e8, sell_meso=0, other_won=0,
                     won_per_eok=2000, options=[mv.Option("메소마켓", 1.0), mv.Option("치장", 0.0)])
    assert out["need"] == 200_000
    # 브론즈(할인 0) → 실버 3% × 100억 = 3억 = 6,000원
    assert out["benefit_won"] == pytest.approx(6000)
    assert [r["label"] for r in out["rows"]] == ["메소마켓", "치장"]
    assert out["rows"][0]["net_cost"] == pytest.approx(-6000)
    assert out["rows"][1]["net_cost"] == pytest.approx(200_000 - 6000)


def test_bundle_api_buys_whole_bundles():
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    body = {"product": "WispsWonderBerry", "table": 1, "unit_price_won": 5400, "spend_won": 250_000,
            "bundle": {"count": 21, "price": 100_000}, "values_eok": {"이그넬라": 5}, "jackpots": ["이그넬라"],
            "won_per_eok": 2000}
    r = c.post("/api/bm/evaluate", json=body).json()
    assert r["pulls"] == 42 and r["spend_won"] == pytest.approx(200_000)  # 21개 × 2묶음, 5만원은 남음
    body["spend_won"] = 50_000
    assert c.post("/api/bm/evaluate", json=body).status_code == 400
