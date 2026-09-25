import json
import shutil
from pathlib import Path

import pytest

from app.models import Submission
from app.store import ROOT, Store


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A throwaway data dir holding copies of the seed problems and keys."""
    for sub in ("problems", "keys"):
        shutil.copytree(ROOT / "data" / sub, tmp_path / sub)
    return tmp_path


@pytest.fixture
def store(data_dir: Path) -> Store:
    return Store(data_dir)


def make_sub(problem_id: str, comments: list[tuple], verdict="changes", confidence=3, elapsed=60) -> Submission:
    """Build a submission from (file, line, text) tuples."""
    return Submission(
        attempt_id=f"20260925-100000-{problem_id}", problem_id=problem_id, submitted_at="2026-09-25T10:00:00",
        elapsed_seconds=elapsed, verdict=verdict, confidence=confidence,
        comments=[{"id": f"c{i}", "file": f, "line": line, "category": "correctness", "text": text}
                  for i, (f, line, text) in enumerate(comments, 1)],
    )


def write_feedback(store: Store, attempt_id: str, grades: dict[str, int], summary="Good.") -> Path:
    path = store.feedback_dir / f"{attempt_id}.json"
    path.write_text(json.dumps({
        "attempt_id": attempt_id, "graded_at": "2026-09-25T10:05:00",
        "comments": [{"comment_id": k, "quality": v, "note": "note"} for k, v in grades.items()],
        "summary": summary,
    }), encoding="utf-8")
    return path
