import pytest

from app.engine.starforce import (
    Events,
    StarforceInput,
    actual_probs,
    base_cost,
    expected,
    max_star_for_level,
    optimize_policy,
    simulate,
)

EOK = 100_000_000  # 1억


def test_base_cost_140_12_matches_calculator():
    # starforcechallenge: 140제 12→13 = 13,051,200 (리서치 03 §3.1)
    assert base_cost(140, 12) == pytest.approx(13_051_200, abs=200)


def test_actual_probs_15_and_29():
    s, d = actual_probs(15)
    assert s == pytest.approx(0.315)
    assert d == pytest.approx(0.02055, abs=1e-5)
    s, d = actual_probs(29)
    assert s == pytest.approx(0.0105)
    assert d == pytest.approx(0.1979, abs=1e-4)


def test_max_star_by_level():
    assert max_star_for_level(250) == 30
    assert max_star_for_level(130) == 20


@pytest.mark.parametrize(
    "level,target,events,meso_eok,destroys",
    [
        # 리서치 03 §7.4 (12성→목표, 기본 복구, 파방 없음, 할인 없음)
        (200, 18, Events.shining(), 16.54, 0.42),  # 인벤 starforce.gg 16.54억/0.43개와 일치
        (200, 18, Events(), 25.57, 0.62),
        (200, 22, Events(), 322.94, 7.49),
        (250, 22, Events.shining(), 314.73, 3.87),
        (160, 17, Events(), 6.19, 0.13),
    ],
)
def test_expected_regression(level, target, events, meso_eok, destroys):
    exp, _ = expected(StarforceInput(level=level, start=12, target=target, events=events))
    assert exp.meso / EOK == pytest.approx(meso_eok, rel=0.005)
    assert exp.destroys == pytest.approx(destroys, abs=0.01)


def test_safeguard_removes_destroys_in_range():
    exp, _ = expected(StarforceInput(level=200, start=15, target=18, safeguard=frozenset({15, 16, 17})))
    assert exp.destroys == pytest.approx(0)


def test_safeguard_costs_triple_without_discount():
    inp = StarforceInput(level=200, start=15, target=16, events=Events(discount30=True),
                         safeguard=frozenset({15}))
    exp, chain = expected(inp)
    bc = base_cost(200, 15)
    assert chain.steps[15].cost == pytest.approx(bc * 0.7 + bc * 2)


def test_mvp_discount_only_up_to_max_star():
    inp = StarforceInput(level=200, start=16, target=18, mvp="diamond", pc_room=True)
    _, chain = expected(inp)
    assert chain.steps[16].cost == pytest.approx(base_cost(200, 16) * 0.85)
    assert chain.steps[17].cost == pytest.approx(base_cost(200, 17))


def test_restore_recovery_returns_to_destroyed_star():
    inp = StarforceInput(level=200, start=17, target=22, recovery={s: "restore" for s in range(15, 22)},
                         spare_price=5 * EOK)
    _, chain = expected(inp)
    assert chain.steps[20].recovery_star == 20
    assert chain.steps[20].recovery_spares == 2


def test_optimal_policy_not_worse_than_default():
    base = StarforceInput(level=200, start=12, target=22, spare_price=10 * EOK)
    default, _ = expected(base)
    pol = optimize_policy(base)
    opt, _ = expected(StarforceInput(**{**base.__dict__, "safeguard": pol.safeguard, "recovery": pol.recovery}))
    assert opt.total <= default.total + 1


def test_simulation_mean_close_to_expectation():
    inp = StarforceInput(level=200, start=12, target=18, events=Events.shining())
    exp, chain = expected(inp)
    dist = simulate(chain, trials=50_000, seed=1)
    assert dist.completed == dist.trials
    assert dist.mean_total == pytest.approx(exp.total, rel=0.03)
    assert dist.percentiles["p50"] <= dist.percentiles["p90"]


def test_restore_meso_uses_level_table():
    inp = StarforceInput(level=250, start=21, target=23, recovery={22: "restore"})
    _, chain = expected(inp)
    assert chain.steps[22].recovery_meso == pytest.approx(472.04 * EOK)
    assert chain.steps[22].recovery_spares == 4


def test_cost_22_to_23_250():
    # 리서치 08: 250제 22→23 = 371,070,400 / 29→30 = 760,357,800
    assert base_cost(250, 22) == pytest.approx(371_070_400, abs=200)
    assert base_cost(250, 29) == pytest.approx(760_357_800, abs=200)
