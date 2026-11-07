import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app

from .conftest import FakePipeline


@pytest.fixture
def build(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>")
    (dist / "assets" / "app-123.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("nope")
    return dist


def client_for(settings, sheets, frontend_dir):
    settings.api.frontend_dir = str(frontend_dir)
    return TestClient(create_app(settings, FakePipeline(), sheets))


def test_serves_the_app_and_its_files(settings, sheets, build):
    with client_for(settings, sheets, build) as c:
        home = c.get("/")
        assert home.status_code == 200 and "<title>app</title>" in home.text
        js = c.get("/assets/app-123.js")
        assert js.text == "console.log(1)" and "immutable" in js.headers["cache-control"]
        assert c.get("/favicon.svg").text == "<svg/>"


def test_app_routes_get_index_html(settings, sheets, build):
    with client_for(settings, sheets, build) as c:
        res = c.get("/logs")
    assert res.status_code == 200 and "<title>app</title>" in res.text


def test_api_still_wins_and_unknown_api_paths_stay_json(settings, sheets, build):
    with client_for(settings, sheets, build) as c:
        assert c.get("/api/health").json()["model"]["ok"] is True
        res = c.get("/api/nope")
        assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"
        assert c.get("/docs").status_code == 200


def test_no_files_outside_the_build_folder(settings, sheets, build):
    with client_for(settings, sheets, build) as c:
        res = c.get("/..%2Fsecret.txt")
    assert "nope" not in res.text


def test_explains_when_the_app_isnt_built(settings, sheets, tmp_path):
    with client_for(settings, sheets, tmp_path / "missing") as c:
        res = c.get("/")
    assert res.status_code == 503 and "npm run build" in res.text


def test_can_be_turned_off(settings, sheets):
    with client_for(settings, sheets, "") as c:
        assert c.get("/").status_code == 404
