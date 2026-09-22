import subprocess

import pytest
from fastapi.testclient import TestClient

import api.main as main_module
from api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A fresh state repo per test, with api.main pointed at it -- STATE is
    read once at import time, so tests have to monkeypatch it directly
    rather than set the env var."""
    monkeypatch.setattr(main_module, "STATE", tmp_path)
    r = main_module.StateRepo(tmp_path)
    r.init()
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path)
    return TestClient(app)


def test_sync_status_route_reports_no_upstream(client):
    resp = client.get("/sync/status")
    assert resp.status_code == 200
    assert resp.json() == {"branch": resp.json()["branch"], "upstream": None, "ahead": 0}


def test_delete_route_erases_a_thing(client):
    mint = client.post("/things", json={
        "kind": "item", "title": "Oops", "gist": "minted by mistake",
    })
    id_ = mint.json()["id"]

    resp = client.delete(f"/things/{id_}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    assert client.get(f"/things/{id_}").status_code == 400
