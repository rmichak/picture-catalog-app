import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    # `with TestClient(app)` triggers FastAPI's lifespan, which runs Base.metadata.create_all().
    with TestClient(app) as c:
        yield c


def test_healthz_ok(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "time" in body
    assert body["dropbox_connected"] is False
    assert body["db_reachable"] is True


def test_root_returns_info_when_no_frontend_built(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "picture-catalog-app"


def test_auth_status_disconnected(client):
    r = client.get("/api/auth/dropbox/status")
    assert r.status_code == 200
    assert r.json()["connected"] is False


def test_folders_requires_dropbox_connection(client):
    r = client.get("/api/folders")
    assert r.status_code == 400


def test_list_photos_empty_on_fresh_install(client):
    r = client.get("/api/photos")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []
