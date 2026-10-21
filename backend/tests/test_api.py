import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def tmp_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(store, "LISTINGS_PATH", tmp_path / "listings.csv")


def test_starforce_endpoint_with_optimize():
    r = client.post("/api/starforce", json={
        "level": 250, "start": 17, "target": 22, "spare_price": 20e8, "optimize": True, "trials": 5000,
        "events": {"discount30": True, "destroy_reduction": True},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expected"]["total"] > 0
    assert body["steps"][0]["star"] == 17
    assert body["policy"] is not None


def test_starforce_rejects_over_max_star():
    r = client.post("/api/starforce", json={"level": 130, "start": 15, "target": 22})
    assert r.status_code == 400


def test_potential_preset_endpoint():
    r = client.post("/api/potential", json={
        "kind": "potential", "part": "top", "level": 250, "current": "unique", "job": "adele", "preset_id": "main33",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["option_prob"] > 0
    assert body["expected_total_meso"] > body["grade_up_expected_meso"]


def test_flame_armor_endpoint():
    r = client.post("/api/flame", json={"item_type": "armor", "level": 250, "boss": True, "threshold": 150})
    assert r.status_code == 200, r.text
    assert 0 < r.json()["prob"] < 1


def test_craft_plan_breakeven():
    r = client.post("/api/craft/plan", json={
        "base_price": 10e8, "market_price": 150e8, "market_other_world": True,
        "starforce": {"level": 200, "start": 0, "target": 18, "trials": 5000},
        "potential": {"part": "gloves", "level": 200, "current": "legendary", "preset_id": "cd1"},
    })
    assert r.status_code == 200, r.text
    c = r.json()["compare"]
    assert c["market_price"] == pytest.approx(165e8)
    assert c["breakeven_price"] == pytest.approx(c["base_price"] + c["craft_expected"])
    assert 0 <= c["loss_probability"] <= 1


def test_listings_roundtrip():
    r = client.post("/api/listings", json={"item_name": "에테르넬 나이트헬름", "star": 22, "price_meso": 300e8})
    assert r.status_code == 200
    lid = r.json()["id"]
    assert len(client.get("/api/listings").json()) == 1
    assert client.delete(f"/api/listings/{lid}").status_code == 200
    assert client.get("/api/listings").json() == []
    assert "1" in (store.LISTINGS_PATH.read_text(encoding="utf-8-sig"))  # 삭제 플래그로 이력 보존


def test_settings_merge_defaults():
    r = client.put("/api/settings", json={"mvp": "gold", "events": {"discount30": True}})
    s = r.json()
    assert s["mvp"] == "gold" and s["events"]["discount30"] is True and s["events"]["plus_one"] is False
