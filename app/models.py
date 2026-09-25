"""Pydantic schemas for problems, answer keys, submissions and feedback files."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Language = Literal["python", "sql", "typescript", "javascript"]
Format = Literal["function", "diff", "multi"]
Difficulty = Literal["easy", "medium", "hard"]
Verdict = Literal["approve", "nits", "changes", "ask"]
Category = Literal["correctness", "security", "performance", "design", "spec"]
Severity = Literal["low", "medium", "high", "critical"]

DEFAULT_TARGET_SECONDS = {"easy": 90, "medium": 180, "hard": 360}
DIFF_PREFIXES = (" ", "+", "-")


class Spec(BaseModel):
    id: str
    text: str


class ProblemFile(BaseModel):
    path: str
    content: str
    is_diff: bool = False

    def rows(self) -> list[dict]:
        """Split content into display rows, parsing the diff marker when is_diff."""
        rows = []
        for raw in self.content.rstrip("\n").split("\n"):
            if self.is_diff:
                kind = raw[:1] if raw[:1] in DIFF_PREFIXES else " "
                text = raw[1:] if raw[:1] in DIFF_PREFIXES else raw
            else:
                kind, text = " ", raw
            rows.append({"kind": kind, "text": text})
        return rows

    @model_validator(mode="after")
    def _check_diff_lines(self) -> ProblemFile:
        if self.is_diff:
            bad = [i + 1 for i, line in enumerate(self.content.rstrip("\n").split("\n")) if line and line[0] not in DIFF_PREFIXES]
            if bad:
                raise ValueError(f"{self.path}: diff lines must start with ' ', '+' or '-' (lines {bad[:5]})")
        return self


class Source(BaseModel):
    kind: Literal["generated", "real"]
    date: str
    repo: str | None = None
    ref: str | None = None
    sha: str | None = None
    dataset: str | None = None
    license: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _real_needs_reference(self) -> Source:
        if self.kind == "real" and not (self.repo and self.ref):
            raise ValueError("real problems need source.repo and source.ref")
        return self


class Problem(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    language: Language
    format: Format
    difficulty: Difficulty
    target_seconds: int | None = None
    spec: Spec
    context: str = ""
    files: list[ProblemFile] = Field(min_length=1)
    source: Source

    @property
    def target(self) -> int:
        return self.target_seconds or DEFAULT_TARGET_SECONDS[self.difficulty]

    def line_count(self, path: str) -> int | None:
        for f in self.files:
            if f.path == path:
                return len(f.rows())
        return None

    def public(self) -> dict:
        """Problem as the browser sees it: rows parsed, no answer key."""
        data = self.model_dump(exclude={"files"})
        data["target_seconds"] = self.target
        data["files"] = [{"path": f.path, "is_diff": f.is_diff, "rows": f.rows()} for f in self.files]
        return data


class KeyIssue(BaseModel):
    id: str
    file: str
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    category: Category
    severity: Severity
    title: str
    explanation: str
    fix: str = ""

    @model_validator(mode="after")
    def _range(self) -> KeyIssue:
        if self.end < self.start:
            raise ValueError(f"issue {self.id}: end before start")
        return self


class AnswerKey(BaseModel):
    problem_id: str
    verdict: Verdict
    issues: list[KeyIssue] = []

    def check_against(self, problem: Problem) -> list[str]:
        """Return problems with this key: unknown files or lines past the end."""
        errors = []
        if self.problem_id != problem.id:
            errors.append(f"key problem_id {self.problem_id} != {problem.id}")
        for issue in self.issues:
            count = problem.line_count(issue.file)
            if count is None:
                errors.append(f"issue {issue.id}: unknown file {issue.file}")
            elif issue.end > count:
                errors.append(f"issue {issue.id}: line {issue.end} past end of {issue.file} ({count} lines)")
        if self.verdict == "changes" and not self.issues:
            errors.append("verdict 'changes' needs at least one issue")
        return errors


class Comment(BaseModel):
    id: str
    file: str
    line: int = Field(ge=1)
    category: Category
    text: str = Field(min_length=1)


class SubmissionIn(BaseModel):
    elapsed_seconds: int = Field(ge=0)
    verdict: Verdict
    confidence: int = Field(ge=1, le=3)
    comments: list[Comment] = []


class Submission(SubmissionIn):
    attempt_id: str
    problem_id: str
    submitted_at: str


class CommentFeedback(BaseModel):
    comment_id: str
    quality: int = Field(ge=0, le=2)
    note: str


class Feedback(BaseModel):
    attempt_id: str
    graded_at: str
    comments: list[CommentFeedback] = []
    summary: str
    key_revised: bool = False
    recap: str | None = None
