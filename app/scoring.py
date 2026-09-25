"""Deterministic scoring of a submission against its answer key, plus Claude's comment grades."""

from __future__ import annotations

from app.models import AnswerKey, Feedback, Problem, Submission

LINE_TOLERANCE = 1
SEVERITY_WEIGHT = {"low": 0.5, "medium": 1.0, "high": 2.0, "critical": 3.0}
WEIGHTS = {"recall": 0.45, "precision": 0.15, "quality": 0.15, "speed": 0.10, "verdict": 0.15}
BAD_APPROVAL_CAP = 30

# Credit for (expected verdict, your verdict). Missing pairs score 0.
VERDICT_CREDIT = {
    "approve": {"approve": 1.0, "nits": 0.75, "ask": 0.25},
    "nits": {"nits": 1.0, "approve": 0.75, "changes": 0.5, "ask": 0.25},
    "changes": {"changes": 1.0, "ask": 0.5},
    "ask": {"ask": 1.0, "changes": 0.5},
}


def match_comments(sub: Submission, key: AnswerKey) -> dict:
    """Pair each comment with the key issue it lands on (same file, within line tolerance)."""
    matches: dict[str, str | None] = {}
    for c in sub.comments:
        # Exact range beats tolerance, and the narrowest range wins, so adjacent issues are not confused.
        same_file = sorted((i for i in key.issues if i.file == c.file), key=lambda i: i.end - i.start)
        hit = next((i for i in same_file if i.start <= c.line <= i.end), None) or next(
            (i for i in same_file if i.start - LINE_TOLERANCE <= c.line <= i.end + LINE_TOLERANCE), None)
        matches[c.id] = hit.id if hit else None
    found = {v for v in matches.values() if v}
    return {"matches": matches, "found": sorted(found), "missed": [i.id for i in key.issues if i.id not in found]}


def calibration_label(confidence: int, verdict_credit: float) -> str:
    right = verdict_credit == 1.0
    if confidence == 3:
        return "sure-right" if right else "overconfident"
    if confidence == 1:
        return "unsure-right" if right else "unsure-wrong"
    return "medium-right" if right else "medium-wrong"


def score(problem: Problem, key: AnswerKey, sub: Submission, feedback: Feedback | None = None) -> dict:
    """Score a submission; quality and the final score need Claude's feedback."""
    m = match_comments(sub, key)
    grades = {c.comment_id: c.quality for c in feedback.comments} if feedback else {}
    if feedback is not None:
        # Quality 0 means Claude judged the comment is not about the issue it landed near.
        m["matches"] = {cid: (kid if kid and grades.get(cid, 0) > 0 else None) for cid, kid in m["matches"].items()}
        found = {v for v in m["matches"].values() if v}
        m["found"] = sorted(found)
        m["missed"] = [i.id for i in key.issues if i.id not in found]
    total_w = sum(SEVERITY_WEIGHT[i.severity] for i in key.issues)
    found_w = sum(SEVERITY_WEIGHT[i.severity] for i in key.issues if i.id in m["found"])
    recall = found_w / total_w if total_w else 1.0
    hit_comments = [cid for cid, kid in m["matches"].items() if kid]
    precision = len(hit_comments) / len(sub.comments) if sub.comments else 1.0

    # Speed only counts as far as the review was accurate, so skimming does not pay.
    raw_speed = min(1.0, problem.target / max(1, sub.elapsed_seconds))
    speed = raw_speed * (recall + precision) / 2

    verdict_credit = VERDICT_CREDIT[key.verdict].get(sub.verdict, 0.0)
    bad_approval = key.verdict == "changes" and sub.verdict in ("approve", "nits")

    quality = None
    final = None
    if feedback is not None:
        if hit_comments:
            quality = sum(grades.get(cid, 0) for cid in hit_comments) / (2 * len(hit_comments))
        else:
            quality = 1.0 if not key.issues and not sub.comments else 0.0
        parts = {"recall": recall, "precision": precision, "quality": quality, "speed": speed, "verdict": verdict_credit}
        final = round(100 * sum(WEIGHTS[k] * v for k, v in parts.items()))
        if bad_approval:
            final = min(final, BAD_APPROVAL_CAP)

    return {
        **m,
        "found_weight": found_w,
        "total_weight": total_w,
        "recall": recall,
        "precision": precision,
        "raw_speed": raw_speed,
        "speed": speed,
        "verdict_credit": verdict_credit,
        "bad_approval": bad_approval,
        "calibration": calibration_label(sub.confidence, verdict_credit),
        "quality": quality,
        "score": final,
    }
