"""다음 단계 장비 후보 (upgrade_paths.yaml + item_catalog.json)."""

from app.engine.next_step import next_steps


def _it(part, name, level, grade="legendary"):
    return {"part": part, "name": name, "level": level, "potential_grade": grade}


def test_armor_next_tier_by_class():
    steps = next_steps(_it("hat", "하이네스 워리어헬름", 150), "warrior")
    assert [s["name"] for s in steps] == ["앱솔랩스 나이트헬름", "아케인셰이드 나이트햇", "에테르넬 나이트헬름"]
    assert all(s["id"] for s in steps)
    assert [s["name"] for s in next_steps(_it("hat", "아케인셰이드 시프햇", 200), "thief")] == ["에테르넬 시프반다나"]
    # 에테르넬 신발·장갑·망토는 없다 → 아케인셰이드가 최상위
    assert next_steps(_it("shoes", "아케인셰이드 나이트슈즈", 200), "warrior") == []
    assert next_steps(_it("hat", "에테르넬 나이트헬름", 250), "warrior") == []
    # 직업 계열을 모르면 카탈로그의 현재 장비 직업으로
    assert [s["name"] for s in next_steps(_it("cape", "앱솔랩스 시프케이프", 160), None)] == ["아케인셰이드 시프케이프"]


def test_weapon_same_type():
    steps = next_steps(_it("weapon", "라이온하트 배틀시미터", 140), "warrior")
    assert [s["name"] for s in steps] == ["앱솔랩스 브로드세이버", "아케인셰이드 투핸드소드"]
    assert [s["name"] for s in next_steps(_it("weapon", "앱솔랩스 튜너", 160), "warrior")] == ["아케인셰이드 튜너"]
    assert next_steps(_it("weapon", "제네시스 튜너", 200), "warrior") == []


def test_accessories_by_level_and_seed_ring():
    assert [s["name"] for s in next_steps(_it("pendant", "도미네이터 펜던트", 140), None)] == ["고통의 근원"]
    assert [s["name"] for s in next_steps(_it("ring", "마이스터링", 140), None)] == ["여명의 가디언 엔젤 링", "거대한 공포"]
    assert next_steps(_it("ring", "리스트레인트 링", 110, grade=None), None) == []
    assert next_steps(_it("emblem", "미트라의 분노 : 전사", 200), None) == []
