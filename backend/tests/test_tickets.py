"""이벤트 아이템(유니크 잠재·에픽 에디 주문서, 17성 강화권) 반영."""

import pytest

from app.engine import recommend as rc
from app.engine import shopping as sh
from app.engine.tickets import Tickets
from tests.test_shopping import CTX, STR, _item


def test_ticket_rules():
    t = Tickets(unique_potential=1, epic_additional=1, star17=1, star17_max_level=200)
    assert t.star_start(160, 0, 22) == 17
    assert t.star_start(250, 0, 22) == 0          # 레벨 상한 초과
    assert t.star_start(160, 0, 17) == 17         # 강화권만으로 목표 도달 → 비용 0
    assert t.star_start(160, 18, 22) == 18
    assert t.grade_start("potential", "rare") == "unique" and t.grade_start("potential", None) == "unique"
    assert t.grade_start("potential", "legendary") == "legendary"
    assert t.grade_start("additional", "rare") == "epic" and t.grade_start("additional", "unique") == "unique"
    assert Tickets().grade_start("potential", "rare") == "rare"


def test_next_targets_cheaper_with_tickets():
    it = {**_item(STR, part="pendant", name="도미네이터 펜던트", slot="펜던트"), "level": 140,
          "next_steps": [{"tier": "칠흑", "name": "고통의 근원", "label": "고통의 근원", "level": 160,
                          "part": "pendant", "id": 1122430}]}
    plain = {(r.star, r.potential): r for r in sh.next_targets(CTX, it, [])}
    ctx = rc.Context(**{**CTX.__dict__, "tickets": Tickets(unique_potential=1, star17=1)})
    rows = {(r.star, r.potential): r for r in sh.next_targets(ctx, it, [])}
    for k, r in rows.items():
        p = plain[k]
        assert r.detail["starforce"] <= p.detail["starforce"] + 1e-6
        assert r.detail["potential"] <= p.detail["potential"] + 1e-6
    k22 = next(k for k in rows if k[0] == 22 and k[1] != "잠재 무관")
    assert rows[k22].cap < plain[k22].cap
    assert any("17성 강화권" in n for n in rows[k22].notes) and any("유니크 잠재" in n for n in rows[k22].notes)
    assert rows[k22].detail["sf_start"] == 17
    assert all(r.detail["starforce"] == 0 for k, r in rows.items() if k[0] == 17)
    assert rows[k22].detail["starforce"] == pytest.approx(
        rc._sf_cost(ctx, 160, 17, 22, ctx.events).total)
