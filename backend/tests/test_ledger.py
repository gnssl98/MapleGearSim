"""강화 가계부: 비용·이벤트·운 계산 (오픈 API 기록 형식 모사)."""

from datetime import date

import pytest

from app.api.ledger import resolve_levels
from app.engine import ledger as lg
from app.engine import potential as pt
from app.engine import starforce as sf
from app.nexon import history as hs


def _sf(before, result="성공", t="2026-10-19T15:00:00+09:00", item="에테르넬 나이트아머", events=None, guard=False):
    after = before + 1 if result == "성공" else (12 if result == "파괴" else before)
    return {"id": f"{item}{before}{t}{result}", "item_upgrade_result": result, "before_starforce_count": before,
            "after_starforce_count": after, "starforce_event_list": events,
            "superior_item_flag": "슈페리얼 장비 미해당",
            "destroy_defence": "파괴 방지 적용" if guard else "파괴 방지 미적용",
            "character_name": "렌쭝쭝", "target_item": item, "date_create": t}


def test_sf_cost_with_mvp_event_and_guard():
    st = lg.SfSettings(mvp="gold", pc_room=True, mvp_max_star=16)
    bc = sf.base_cost(250, 15)
    assert lg.sf_attempt_cost(_sf(15), 250, st) == pytest.approx(bc * (1 - 0.05 - 0.05))
    ev = [{"cost_discount_rate": "30", "destroy_decrease_rate": "30", "starforce_event_range": "0~21"}]
    assert lg.sf_attempt_cost(_sf(15, events=ev), 250, st) == pytest.approx(bc * 0.9 * 0.7)
    assert lg.sf_attempt_cost(_sf(17, guard=True), 250, st) == pytest.approx(sf.base_cost(250, 17) * 3)
    succ, dest = lg.sf_probs(_sf(17, events=ev))
    assert dest == pytest.approx(sf.actual_probs(17)[1] * 0.7)
    assert lg.sf_probs(_sf(17, guard=True))[1] == 0
    # 범위 밖 이벤트는 무시
    assert lg.sf_event(_sf(22, events=ev)).discount == 0


def test_tail_and_mid_p():
    assert lg.tail_at_least([0.5, 0.5], 1) == pytest.approx(0.75)
    assert lg.tail_at_least([0.5, 0.5], 3) == 0
    luck = lg.Luck()
    luck.add(0.3, False)
    assert luck.to_dict()["below"] == pytest.approx(0.35)  # 0회 파괴 (기대 0.3) → 운 좋은 편


def test_sessions_split_on_discontinuity():
    rows = [_sf(0, t="T1"), _sf(1, t="T2"), _sf(5, t="T3"), _sf(6, "파괴", t="T4"), _sf(12, t="T5")]
    sess = lg.sf_sessions(rows)
    assert [len(s) for s in sess] == [2, 3]


def test_build_totals_and_grade_luck():
    pot = {"character_name": "웅쭝쭝", "date_create": "2026-10-19T17:00:00+09:00", "potential_type": "잠재능력 재설정",
           "item_upgrade_result": "성공", "miracle_time_flag": "이벤트 적용되지 않음", "item_level": 200,
           "target_item": "아케인셰이드 나이트슈즈", "potential_option_grade": "에픽",
           "additional_potential_option_grade": None, "upgrade_guarantee": False}
    add = {**pot, "potential_type": "에디셔널 잠재능력 재설정", "item_upgrade_result": "실패",
           "additional_potential_option_grade": "레전드리"}
    cube = {**pot, "cube_type": "카르마 블랙 큐브", "item_upgrade_result": "실패", "potential_option_grade": "유니크"}
    hist = {"starforce": [_sf(0), _sf(1), _sf(2, "실패(유지)")], "potential": [pot, add], "cube": [cube]}
    out = lg.build(hist, {"에테르넬 나이트아머": 250}, lg.SfSettings(), {"카르마 블랙 큐브": 5e6})
    sf_total = sum(sf.base_cost(250, s) for s in (0, 1, 2))
    assert out["totals"]["starforce"] == pytest.approx(sf_total)
    # 성공한 재설정은 시도 전 등급(레어) 비용, 에디는 레전 비용
    assert out["totals"]["potential"] == pytest.approx(pt.cost_per_attempt("potential", 200, "rare")
                                                       + pt.cost_per_attempt("additional", 200, "legendary"))
    assert out["totals"]["cube"] == 5e6
    g = out["luck"]["grade_up"]
    assert g["attempts"] == 2 and g["actual"] == 1  # 레어→에픽 성공 + 블랙 큐브 유니크 실패 (레전 에디는 제외)
    assert g["expected"] == pytest.approx(0.15 + 0.014)
    assert out["luck"]["starforce_cost"]["sessions"] == 1
    assert out["daily"][0]["attempts"] == 6


def test_unknown_level_and_resolve():
    hist = {"starforce": [_sf(0, item="수상한 벨트")], "potential": [], "cube": []}
    assert lg.build(hist, {}, lg.SfSettings())["unknown_levels"] == {"수상한 벨트": 1}
    hist2 = {"starforce": [_sf(0), _sf(0, item="노블 브레이슬릿")],
             "potential": [{"target_item": "노블 브레이슬릿", "item_level": 100}], "cube": []}
    assert resolve_levels(hist2, {}) == {"에테르넬 나이트아머": 250, "노블 브레이슬릿": 100}
    assert resolve_levels(hist2, {"노블 브레이슬릿": 120})["노블 브레이슬릿"] == 120


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, path, params, refresh=False):
        self.calls.append((path, dict(params), refresh))
        if params.get("cursor") == "c1":
            return {"starforce_history": [{"id": "b"}], "next_cursor": None}
        if "starforce" in path and params.get("date") == "2026-10-19":
            return {"starforce_history": [{"id": "a"}, {"id": "a"}], "next_cursor": "c1"}
        return {f"{path.rsplit('/', 1)[1]}_history": [], "next_cursor": None}


def test_fetch_paginates_dedupes_and_refreshes_recent():
    c = FakeClient()
    out = hs.fetch(date(2026, 10, 18), date(2026, 10, 25), today=date(2026, 10, 20), client=c,
                   kinds=("starforce",))
    assert [r["id"] for r in out["starforce"]] == ["a", "b"]
    dates = {p["date"]: r for _, p, r in c.calls if "date" in p}
    assert dates == {"2026-10-18": False, "2026-10-19": True, "2026-10-20": True}  # 미래 날짜는 잘라냄
    with pytest.raises(ValueError):
        hs.fetch(date(2026, 1, 1), date(2026, 10, 1), today=date(2026, 10, 20), client=c)
