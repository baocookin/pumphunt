import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import api
from app.config import settings
from app.engine import OnDemandLimit
from app.rpc import BudgetExhausted

MINT = "So11111111111111111111111111111111111111112"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "run_engine", False)
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "password", "pw")
    (tmp_path / "sniper-2026-10-07.jsonl").write_text('{"a": 1}\n')
    with TestClient(api.app) as c:
        yield c


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "ray" and body["auth"] is True and body["filters_frozen"] is True


def test_the_dashboard_and_api_need_the_password(client):
    r = client.get("/api/state")
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    assert client.get("/api/state", auth=("x", "wrong")).status_code == 401
    r = client.get("/api/state", auth=("anyone", "pw"))
    assert r.status_code == 200 and r.json()["live"] == [] and r.json()["recent"] == []
    page = client.get("/", auth=("anyone", "pw"))
    assert page.status_code == 200 and "Rây" in page.text
    assert client.get("/").status_code == 401


def test_without_a_password_everything_private_is_locked(client, monkeypatch):
    monkeypatch.setattr(settings, "password", None)
    assert client.get("/api/state").status_code == 503
    assert client.get("/").status_code == 503
    assert client.get("/api/health").status_code == 200


def test_the_locked_answer_says_when_a_password_was_sent(client, monkeypatch):
    monkeypatch.setattr(settings, "password", None)
    assert "đã gửi mật khẩu" not in client.get("/api/state").json()["detail"]
    r = client.get("/api/state", auth=("a", "b"))
    assert r.status_code == 503 and "đã gửi mật khẩu" in r.json()["detail"]
    assert "đã gửi mật khẩu" in client.get("/", auth=("a", "b")).text


def test_no_answer_may_be_kept_by_the_cdn(client):
    for path, auth in (("/api/health", None), ("/api/state", ("a", "pw")), ("/", ("a", "pw")), ("/", None)):
        r = client.get(path, auth=auth)
        assert r.headers["cache-control"] == "no-store, private", (path, r.status_code)
    r = client.get("/api/export/file/sniper-2026-10-07.jsonl")
    assert r.headers["cache-control"] == "no-store, private"


def test_the_report_and_the_journal_files_need_the_password(client, tmp_path):
    (tmp_path / "ray").mkdir(exist_ok=True)
    (tmp_path / "ray" / "outcomes-2026-10-09.jsonl").write_text("")
    (tmp_path / "ray" / "credits.json").write_text("{}")
    for path in ("/api/report", "/api/journal", "/api/journal/outcomes-2026-10-09.jsonl"):
        assert client.get(path).status_code == 401
    r = client.get("/api/report?days=7", auth=("a", "pw"))
    assert r.status_code == 200 and r.json()["totals"]["settled"] == 0 and r.json()["pool"]["n"] == 206
    assert {"model", "candidates"} <= r.json().keys()  # None until an engine runs
    files = client.get("/api/journal", auth=("a", "pw")).json()["files"]
    assert [f["name"] for f in files] == ["outcomes-2026-10-09.jsonl"]
    assert client.get("/api/journal/outcomes-2026-10-09.jsonl", auth=("a", "pw")).status_code == 200
    assert client.get("/api/journal/credits.json", auth=("a", "pw")).status_code == 404
    assert "ray" not in [f["name"] for f in client.get("/api/files").json()["files"]]


def test_scoring_needs_a_valid_mint_and_a_running_engine(client):
    assert client.post("/api/score/not-a-mint", auth=("a", "pw")).status_code == 400
    assert client.post(f"/api/score/{MINT}", auth=("a", "pw")).status_code == 503
    assert client.get(f"/api/token/{MINT}", auth=("a", "pw")).status_code == 404


def test_the_research_files_stay_downloadable(client):
    files = client.get("/api/files").json()["files"]
    assert [f["name"] for f in files] == ["sniper-2026-10-07.jsonl"]
    r = client.get("/api/export/file/sniper-2026-10-07.jsonl")
    assert r.status_code == 200 and r.text == '{"a": 1}\n'
    assert client.get("/api/export/file/..%2Fsecret.jsonl").status_code == 404
    assert client.get("/api/export/file/ray").status_code == 404


class _Beating:
    def __init__(self, alive_ago, poll_ago):
        now = time.time()
        self.stats = {"alive": {"poll": now - alive_ago}, "last_poll": now - poll_ago}


def test_health_fails_only_when_the_poll_loop_is_stuck(client, monkeypatch):
    monkeypatch.setattr(api.state, "engine", _Beating(alive_ago=2, poll_ago=900))  # reads fail, loop runs
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["poll_age_s"] > 800
    monkeypatch.setattr(api.state, "engine", _Beating(alive_ago=400, poll_ago=400))  # loop stuck
    assert client.get("/api/health").status_code == 503


class _Failing:
    def __init__(self, exc):
        self.exc = exc

    async def score_mint(self, mint):
        raise self.exc


def test_a_failed_score_answers_without_the_rpc_url(client, monkeypatch):
    url = "https://rpc.example/?api-key=SECRET"
    req = httpx.Request("POST", url)
    resp = httpx.Response(503, request=req)
    cases = [
        (OnDemandLimit("hết lượt"), 429),
        (LookupError("không thấy"), 404),
        (BudgetExhausted("ondemand"), 503),
        (httpx.HTTPStatusError(f"for url '{url}'", request=req, response=resp), 502),
        (httpx.ConnectError(f"cannot reach {url}"), 502),
        (ValueError(f"odd answer from {url}"), 500),
    ]
    for exc, status in cases:
        monkeypatch.setattr(api.state, "engine", _Failing(exc))
        r = client.post(f"/api/score/{MINT}", auth=("a", "pw"))
        assert r.status_code == status and "SECRET" not in r.text, (exc, r.status_code, r.text)
