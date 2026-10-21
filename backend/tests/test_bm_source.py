"""확률형 BM 출처: 고정=스냅숏, 이벤트=월간 캐시, 공지 매칭."""

from datetime import date

import pytest

from app.engine import bm_source as src


def test_notice_matching():
    notices = [{"title": "9월 17일 캐시아이템 업데이트 스페셜 루나 크리스탈", "date": "2026-09-17"},
               {"title": "9월 17일 캐시아이템 업데이트 위습의 원더베리 & 루나 크리스탈", "date": "2026-09-17"},
               {"title": "9월 17일 캐시아이템 업데이트 로얄스타일 & 마스터피스", "date": "2026-09-17"}]
    assert "원더베리" in src.notice_for("루나 크리스탈 스윗", notices)["title"]
    assert "스페셜" in src.notice_for("스페셜 루나 크리스탈 드림", notices)["title"]
    assert "원더베리" in src.notice_for("위습의 원더베리", notices)["title"]
    assert "마스터피스" in src.notice_for("마스터피스 레드", notices)["title"]
    assert src.notice_for("골드 애플", notices) is None


def test_stale():
    assert src.is_stale(None)
    assert src.is_stale({"fetched_at": "2026-09-01T10:00:00"}, today=date(2026, 10, 1))
    assert not src.is_stale({"fetched_at": "2026-09-20T10:00:00"}, today=date(2026, 10, 1))


def test_fixed_uses_snapshot_event_uses_cache(tmp_path, monkeypatch):
    cache = tmp_path / "tables.json"
    cache.write_text('{"fetched_at": "2026-10-01T00:00:00", "notices": [], "products": ['
                     '{"id": "RoyalStyle", "name": "로얄스타일", "url": "u", "tables": [{"title": "새 구성", "rows": [{"group": "", "item": "새 템", "prob": 1.0}], "total": 1.0}]},'
                     '{"id": "GoldApple", "name": "골드 애플", "url": "u", "tables": [{"title": "가짜", "rows": [{"group": "", "item": "가짜", "prob": 1.0}], "total": 1.0}]}]}',
                     encoding="utf-8")
    monkeypatch.setattr(src, "CACHE_PATH", cache)
    src.load.cache_clear()
    try:
        by = {p["id"]: p for p in src.load()["products"]}
        assert by["RoyalStyle"]["source"] == "monthly" and by["RoyalStyle"]["tables"][0]["title"] == "새 구성"
        assert by["GoldApple"]["source"] == "snapshot" and by["GoldApple"]["tables"][0]["title"] != "가짜"
        assert by["RoyalStyle"]["default_price"] == 2200
        ww = by["WispsWonderBerry"]
        assert [o["count"] for o in ww["options"]] == [1, 11, 21]
        assert ww["options"][ww["best_option"]]["count"] == 21  # 개당 4,762원이 가장 쌈
        assert ww["default_price"] == pytest.approx(100000 / 21)
    finally:
        src.load.cache_clear()
