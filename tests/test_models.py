import pytest
from pydantic import ValidationError

from app.models import AnswerKey, Problem, ProblemFile, Source


def test_every_seed_problem_has_a_consistent_key(store):
    problems = store.problems()
    assert len(problems) == len(list(store.problems_dir.glob("*.json")))
    for p in problems:
        key = store.key(p.id)
        assert key is not None, p.id
        assert key.check_against(p) == [], p.id


def test_seed_covers_languages_formats_and_sources(store):
    problems = store.problems()
    assert {p.language for p in problems} >= {"python", "sql", "typescript", "javascript"}
    assert {p.format for p in problems} == {"function", "diff", "multi"}
    assert {p.difficulty for p in problems} == {"easy", "medium", "hard"}
    assert {p.source.kind for p in problems} == {"generated", "real"}
    assert {store.key(p.id).verdict for p in problems} >= {"approve", "nits", "changes"}


def test_diff_rows_parse_markers():
    f = ProblemFile(path="a.ts", is_diff=True, content=" keep\n-old\n+new\n")
    assert f.rows() == [{"kind": " ", "text": "keep"}, {"kind": "-", "text": "old"}, {"kind": "+", "text": "new"}]


def test_diff_rejects_unmarked_lines():
    with pytest.raises(ValidationError, match="must start with"):
        ProblemFile(path="a.ts", is_diff=True, content="+ok\nbad\n")


def test_real_source_needs_reference():
    with pytest.raises(ValidationError, match="repo and source.ref"):
        Source(kind="real", date="2020-01-01")


def test_key_check_flags_bad_lines_and_files(store):
    p = store.problem("py-orders-pagination")
    key = AnswerKey.model_validate({"problem_id": p.id, "verdict": "changes", "issues": [
        {"id": "a", "file": "orders/queries.py", "start": 17, "end": 18, "category": "spec", "severity": "low", "title": "t", "explanation": "e"},
        {"id": "b", "file": "nope.py", "start": 1, "end": 1, "category": "spec", "severity": "low", "title": "t", "explanation": "e"},
    ]})
    errors = key.check_against(p)
    assert any("past end" in e for e in errors) and any("unknown file" in e for e in errors)


def test_changes_verdict_needs_issues(store):
    p = store.problem("py-retry-backoff")
    key = AnswerKey(problem_id=p.id, verdict="changes", issues=[])
    assert key.check_against(p) == ["verdict 'changes' needs at least one issue"]


def test_public_problem_hides_key_and_sets_target(store):
    public = store.problem("py-orders-pagination").public()
    assert public["target_seconds"] == 180
    assert "verdict" not in public and "issues" not in public
    assert public["files"][0]["rows"][2]["text"] == "    offset = page * page_size"


def test_problem_id_pattern():
    with pytest.raises(ValidationError):
        Problem.model_validate({"id": "Bad Id", "title": "t", "language": "python", "format": "function",
                                "difficulty": "easy", "spec": {"id": "x", "text": "y"},
                                "files": [{"path": "a.py", "content": "x"}], "source": {"kind": "generated", "date": "d"}})
