import json

import pytest

from app import cli
from app.models import SubmissionIn
from tests.conftest import write_feedback


@pytest.fixture
def attempt(store, monkeypatch):
    monkeypatch.setenv("REVIEW_DRILL_DATA", str(store.data_dir))
    sub = store.save_submission("py-orders-pagination", SubmissionIn(elapsed_seconds=90, verdict="changes", confidence=3, comments=[
        {"id": "c1", "file": "orders/queries.py", "line": 4, "category": "security", "text": "injection"},
        {"id": "c2", "file": "orders/queries.py", "line": 14, "category": "design", "text": "index access is fragile"},
    ]))
    return sub


def test_pending_prints_bundle(attempt, capsys):
    assert cli.main(["pending"]) == 0
    out = capsys.readouterr().out
    assert attempt.attempt_id in out
    assert "-> HIT k2" in out and "-> FALSE ALARM" in out
    assert "Missed: ['k1', 'k3']" in out
    template = json.loads(out[out.index("Template:") + len("Template:"):].strip())
    assert [c["comment_id"] for c in template["comments"]] == ["c1", "c2"]


def test_pending_empty_after_grading(attempt, store, capsys):
    write_feedback(store, attempt.attempt_id, {"c1": 2, "c2": 1})
    cli.main(["pending"])
    assert "No submissions waiting" in capsys.readouterr().out


def test_show_latest_includes_feedback(attempt, store, capsys):
    write_feedback(store, attempt.attempt_id, {"c1": 2, "c2": 1}, summary="nice")
    assert cli.main(["show", "latest"]) == 0
    assert '"summary": "nice"' in capsys.readouterr().out


def test_stats_prints_json(attempt, store, capsys):
    write_feedback(store, attempt.attempt_id, {"c1": 2, "c2": 0})
    assert cli.main(["stats"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["graded"] == 1 and data["miss_rate_by_language"]["python"] == round(2 / 3, 3)


def test_validate_all_ok(attempt, capsys):
    assert cli.main(["validate"]) == 0
    assert "FAIL" not in capsys.readouterr().out


def test_validate_catches_feedback_mismatch(attempt, store, capsys):
    path = write_feedback(store, attempt.attempt_id, {"c1": 2, "c9": 1})
    assert cli.main(["validate", str(path)]) == 1
    out = capsys.readouterr().out
    assert "unknown comment_id c9" in out and "comment c2 not graded" in out


def test_validate_catches_bad_key(attempt, store, capsys):
    path = store.keys_dir / "py-orders-pagination.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["issues"][0]["end"] = 40
    path.write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["validate", str(path)]) == 1
    assert "past end" in capsys.readouterr().out


def test_validate_flags_problem_without_key(attempt, store, capsys):
    (store.keys_dir / "ts-format-price.json").unlink()
    assert cli.main(["validate"]) == 1
    assert "missing file" in capsys.readouterr().out
