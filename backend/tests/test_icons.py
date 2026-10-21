"""아이콘: 장착 장비는 넥슨 URL 리다이렉트, 나머지는 카탈로그 id."""

from fastapi.testclient import TestClient

from app.api import icons
from app.main import app


def test_icon_by_name(tmp_path, monkeypatch):
    (tmp_path / "maplestory_v1_character_item-equipment_x.json").write_text(
        '{"body": {"item_equipment": [{"item_name": "블랙빈 마크", "item_icon": "https://open.api.nexon.com/i/A"}]}}',
        encoding="utf-8")
    (tmp_path / "icons").mkdir()
    (tmp_path / "icons" / "1122430.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(icons, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(icons, "ICON_DIR", tmp_path / "icons")
    monkeypatch.setattr(icons, "_equipped_at", 0.0)
    c = TestClient(app)
    r = c.get("/api/icon/by-name", params={"name": "블랙빈 마크"}, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "https://open.api.nexon.com/i/A"
    r = c.get("/api/icon/by-name", params={"name": "고통의 근원"})
    assert r.status_code == 200 and r.content == b"\x89PNG"
    assert c.get("/api/icon/by-name", params={"name": "없는 장비"}).status_code == 404
