"""File-based storage for problems, keys, submissions and feedback under the data dir."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.models import AnswerKey, Feedback, Problem, Submission, SubmissionIn

ROOT = Path(__file__).resolve().parent.parent


class Store:
    """Reads and writes the JSON files that make up the app's state."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir or os.environ.get("REVIEW_DRILL_DATA") or ROOT / "data")
        self.problems_dir = self.data_dir / "problems"
        self.keys_dir = self.data_dir / "keys"
        self.submissions_dir = self.data_dir / "submissions"
        self.feedback_dir = self.data_dir / "feedback"
        for d in (self.problems_dir, self.keys_dir, self.submissions_dir, self.feedback_dir):
            d.mkdir(parents=True, exist_ok=True)

    def _read(self, path: Path, model: type[BaseModel]):
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, model: BaseModel) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(model.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        tmp.replace(path)

    def problems(self) -> list[Problem]:
        """Load every valid problem, skipping files that fail validation."""
        out = []
        for path in sorted(self.problems_dir.glob("*.json")):
            try:
                out.append(self._read(path, Problem))
            except ValueError:
                continue
        return out

    def problem(self, problem_id: str) -> Problem | None:
        path = self.problems_dir / f"{problem_id}.json"
        return self._read(path, Problem) if path.exists() else None

    def key(self, problem_id: str) -> AnswerKey | None:
        path = self.keys_dir / f"{problem_id}.json"
        return self._read(path, AnswerKey) if path.exists() else None

    def save_submission(self, problem_id: str, data: SubmissionIn, now: datetime | None = None) -> Submission:
        now = now or datetime.now()
        attempt_id = f"{now:%Y%m%d-%H%M%S}-{problem_id}"
        sub = Submission(**data.model_dump(), attempt_id=attempt_id, problem_id=problem_id,
                         submitted_at=now.isoformat(timespec="seconds"))
        self._write(self.submissions_dir / f"{attempt_id}.json", sub)
        return sub

    def submissions(self) -> list[Submission]:
        out = []
        for path in sorted(self.submissions_dir.glob("*.json")):
            try:
                out.append(self._read(path, Submission))
            except ValueError:
                continue
        return out

    def submission(self, attempt_id: str) -> Submission | None:
        path = self.submissions_dir / f"{attempt_id}.json"
        return self._read(path, Submission) if path.exists() else None

    def feedback(self, attempt_id: str) -> Feedback | None:
        """Load feedback, returning None when missing or not valid yet."""
        path = self.feedback_dir / f"{attempt_id}.json"
        if not path.exists():
            return None
        try:
            return self._read(path, Feedback)
        except ValueError:
            return None

    def feedback_error(self, attempt_id: str) -> str | None:
        """Return the validation error for a feedback file, if it has one."""
        path = self.feedback_dir / f"{attempt_id}.json"
        if not path.exists():
            return None
        try:
            self._read(path, Feedback)
        except ValueError as e:
            return str(e)
        return None
