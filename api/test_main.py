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


def test_mint_route_defaults_name_to_the_slugified_title(client):
    mint = client.post("/things", json={
        "kind": "item", "title": "A New Thing", "gist": "g",
    })
    id_ = mint.json()["id"]
    assert client.get(f"/things/{id_}").json()["name"] == "a-new-thing"


def test_things_carries_the_container_chain_for_each_thing(client):
    """Search runs off this payload, and a result you cannot place is half an
    answer -- "Mobile fan a" tells you nothing you did not already know."""
    def mint(kind, title):
        return client.post("/things", json={
            "kind": kind, "title": title, "gist": ""}).json()["id"]

    house, shelf, fan = mint("container", "House"), mint("container", "Shelf"), mint("item", "Fan")
    client.post(f"/things/{house}/place", json={"container": None})
    client.post(f"/things/{shelf}/place", json={"container": house})
    client.post(f"/things/{fan}/place", json={"container": shelf})

    where = {t["title"]: t["where"] for t in client.get("/things").json()["things"]}
    assert where["Fan"] == ["House", "Shelf"]
    assert where["House"] == []


def test_the_home_page_keeps_results_out_of_the_containers_card(client):
    """Results are any kind at any depth, which is not what "Containers"
    means. Sharing one card would render a missed search as
    "Containers / Nothing yet"."""
    page = client.get("/m").text
    assert 'id="searchInput"' in page
    assert 'id="resultsCard" style="display:none"' in page
    assert 'id="containersCard"' in page


def test_the_photo_and_the_replace_badge_are_separate_tap_targets(client):
    """The thumbnail crops to 4:3, so tapping it has to open the full frame.
    That only works if the surrounding box has no tap handler of its own --
    it used to, and it swallowed the whole photo to open the file picker."""
    id_ = client.post("/things", json={
        "kind": "item", "title": "Photographed", "gist": "g"}).json()["id"]
    page = client.get(f"/m/{id_}").text

    assert '<div class="photoBox">' in page          # no onclick on the box
    assert 'onclick="openPhoto()"' in page
    assert page.count("photoInput').click()") == 2   # badge and placeholder


def test_health_reports_the_printer_but_never_fails_on_it(client, monkeypatch):
    """The relay runs on another machine. An absent one is an ordinary state,
    so it has to show in the payload without moving `ok` -- `ok` is what the
    container healthcheck and the ingress probe read, and an unplugged printer
    must not take the service down."""
    assert client.get("/health").json() == {"ok": True, "printer": False}

    monkeypatch.setattr(main_module, "_relay", object())
    assert client.get("/health").json() == {"ok": True, "printer": True}


def test_a_thing_page_says_so_when_no_print_client_is_connected(client, monkeypatch):
    """Otherwise the first sign is a 503 after you have already chosen a
    caption and a medium."""
    id_ = client.post("/things", json={
        "kind": "item", "title": "Labelled", "gist": "g"}).json()["id"]

    assert "Print client offline" in client.get(f"/m/{id_}").text

    monkeypatch.setattr(main_module, "_relay", object())
    assert "Print client offline" not in client.get(f"/m/{id_}").text


def test_title_route_edits_the_h1(client):
    mint = client.post("/things", json={"kind": "item", "title": "Oops", "gist": "g"})
    id_ = mint.json()["id"]

    resp = client.put(f"/things/{id_}/title", json={"title": "Fixed title"})
    assert resp.status_code == 200, resp.text
    assert client.get(f"/things/{id_}").json()["title"] == "Fixed title"


def test_gist_route_edits_the_gist(client):
    mint = client.post("/things", json={"kind": "item", "title": "Thing", "gist": "old"})
    id_ = mint.json()["id"]

    resp = client.put(f"/things/{id_}/gist", json={"gist": "new gist"})
    assert resp.status_code == 200, resp.text
    assert client.get(f"/things/{id_}").json()["gist"] == "new gist"


@pytest.fixture
def client_with_remote(client, tmp_path):
    """`client`'s state repo pushed to a bare remote -- siblings of tmp_path,
    never inside it, or a real state doc could mistake it for repo content."""
    bare = tmp_path.parent / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)])
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=tmp_path)
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=tmp_path,
                    capture_output=True, text=True)
    return client, bare, branch


def test_sync_pulls_a_fast_forward_then_pushes(client_with_remote, tmp_path):
    client, bare, branch = client_with_remote

    # A second clone, standing in for a different writer to the same remote --
    # the exact scenario that left htpc's production clone stale for real.
    other = tmp_path.parent / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)])
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=other)
    subprocess.run(["git", "config", "user.name", "Other"], cwd=other)
    (other / "kb" / "note.txt").write_text("from elsewhere")
    subprocess.run(["git", "add", "-A"], cwd=other)
    subprocess.run(["git", "commit", "-q", "-m", "from elsewhere"], cwd=other)
    subprocess.run(["git", "push", "-q", "origin", branch], cwd=other)

    resp = client.post("/sync")
    assert resp.status_code == 200, resp.text
    assert (tmp_path / "kb" / "note.txt").read_text() == "from elsewhere"


def test_sync_refuses_a_real_divergence(client_with_remote, tmp_path):
    client, bare, branch = client_with_remote

    other = tmp_path.parent / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)])
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=other)
    subprocess.run(["git", "config", "user.name", "Other"], cwd=other)
    (other / "kb" / "note.txt").write_text("from elsewhere")
    subprocess.run(["git", "add", "-A"], cwd=other)
    subprocess.run(["git", "commit", "-q", "-m", "from elsewhere"], cwd=other)
    subprocess.run(["git", "push", "-q", "origin", branch], cwd=other)

    # Local also moves, independently -- a true two-way divergence, not
    # just "behind."
    client.post("/things", json={"kind": "item", "title": "Local", "gist": "g"})

    resp = client.post("/sync")
    assert resp.status_code == 409
    assert "diverged" in resp.json()["detail"]
    # Refused cleanly -- no half-finished merge left on disk.
    status = subprocess.run(["git", "status", "--short"], cwd=tmp_path,
                             capture_output=True, text=True).stdout
    assert "UU" not in status and "AA" not in status
