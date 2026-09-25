import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import write_feedback

ORDERS = "orders/queries.py"


@pytest.fixture
def client(data_dir):
    app = create_app(data_dir, watch_files=False)
    with TestClient(app) as c:
        c.app_store = app.state.store
        yield c


def submit(client, problem_id="py-orders-pagination", comments=None, verdict="changes"):
    body = {"elapsed_seconds": 95, "verdict": verdict, "confidence": 2, "comments": comments if comments is not None else [
        {"id": "c1", "file": ORDERS, "line": 4, "category": "security", "text": "SQL injection, use placeholders"},
        {"id": "c2", "file": ORDERS, "line": 5, "category": "performance", "text": "fetchall loads everything"},
    ]}
    return client.post(f"/api/problems/{problem_id}/submit", json=body)


def test_list_problems(client):
    res = client.get("/api/problems")
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert "py-orders-pagination" in ids and "real-thefuck-php-s" in ids
    assert all(p["latest"] is None for p in res.json())


def test_problem_detail_does_not_leak_key(client):
    res = client.get("/api/problems/py-orders-pagination")
    assert res.status_code == 200
    text = res.text
    assert "SQL injection" not in text and '"issues"' not in text


def test_unknown_problem_404(client):
    assert client.get("/api/problems/nope").status_code == 404
    assert submit(client, "nope").status_code == 404


def test_submit_rejects_comment_outside_code(client):
    res = submit(client, comments=[{"id": "c1", "file": ORDERS, "line": 99, "category": "spec", "text": "x"}])
    assert res.status_code == 422
    res = submit(client, comments=[{"id": "c1", "file": "other.py", "line": 1, "category": "spec", "text": "x"}])
    assert res.status_code == 422


def test_submit_rejects_bad_payload(client):
    res = client.post("/api/problems/py-orders-pagination/submit", json={"elapsed_seconds": 5, "verdict": "maybe", "confidence": 2})
    assert res.status_code == 422


def test_submit_then_feedback_flow(client):
    res = submit(client)
    assert res.status_code == 200
    view = res.json()
    attempt_id = view["attempt_id"]
    assert view["result"]["found"] == ["k2"] and view["result"]["score"] is None
    assert view["key"]["verdict"] == "changes"
    assert (client.app_store.submissions_dir / f"{attempt_id}.json").exists()

    latest = next(p for p in client.get("/api/problems").json() if p["id"] == "py-orders-pagination")["latest"]
    assert latest["attempt_id"] == attempt_id and latest["graded"] is False

    write_feedback(client.app_store, attempt_id, {"c1": 2, "c2": 0}, summary="Caught the injection.")
    view = client.get(f"/api/attempts/{attempt_id}").json()
    assert view["feedback"]["summary"] == "Caught the injection."
    assert view["result"]["quality"] == 1 and isinstance(view["result"]["score"], int)

    hist = client.get("/api/history").json()
    assert hist[0]["attempt_id"] == attempt_id and hist[0]["graded"] and hist[0]["false_alarms"] == 1
    stats = client.get("/api/stats").json()
    assert stats["graded"] == 1
    assert stats["miss_rate_by_category"]["security"] == 0
    assert stats["verdict_right_by_confidence"] == {"2": 1.0}


def test_invalid_feedback_reports_error(client):
    attempt_id = submit(client).json()["attempt_id"]
    (client.app_store.feedback_dir / f"{attempt_id}.json").write_text('{"attempt_id": "x"}', encoding="utf-8")
    view = client.get(f"/api/attempts/{attempt_id}").json()
    assert view["feedback"] is None and "summary" in view["feedback_error"]


def test_unknown_attempt_404(client):
    assert client.get("/api/attempts/nope").status_code == 404


def test_serves_ui(client):
    assert "Review Drill" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
