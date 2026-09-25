"""Combine submissions with keys and feedback into attempt views, history and stats."""

from __future__ import annotations

from collections import defaultdict

from app.models import Submission
from app.scoring import score
from app.store import Store


def attempt_view(store: Store, sub: Submission) -> dict | None:
    """Full graded view of one attempt, or None if its problem or key is gone."""
    problem = store.problem(sub.problem_id)
    key = store.key(sub.problem_id)
    if problem is None or key is None:
        return None
    fb = store.feedback(sub.attempt_id)
    return {
        "attempt_id": sub.attempt_id,
        "problem": problem.public(),
        "submission": sub.model_dump(),
        "key": key.model_dump(),
        "result": score(problem, key, sub, fb),
        "feedback": fb.model_dump() if fb else None,
        "feedback_error": store.feedback_error(sub.attempt_id),
    }


def history(store: Store) -> list[dict]:
    """All attempts, newest first, with the fields the History table needs."""
    rows = []
    for sub in store.submissions():
        view = attempt_view(store, sub)
        if view is None:
            continue
        p, r = view["problem"], view["result"]
        rows.append({
            "attempt_id": sub.attempt_id,
            "problem_id": p["id"],
            "title": p["title"],
            "language": p["language"],
            "difficulty": p["difficulty"],
            "source": p["source"]["kind"],
            "submitted_at": sub.submitted_at,
            "verdict": sub.verdict,
            "expected_verdict": view["key"]["verdict"],
            "verdict_credit": r["verdict_credit"],
            "confidence": sub.confidence,
            "found": len(r["found"]),
            "issues": len(view["key"]["issues"]),
            "false_alarms": sum(1 for v in r["matches"].values() if v is None),
            "elapsed_seconds": sub.elapsed_seconds,
            "target_seconds": p["target_seconds"],
            "score": r["score"],
            "graded": view["feedback"] is not None,
        })
    rows.sort(key=lambda r: r["submitted_at"], reverse=True)
    return rows


def _rate(hit: int, total: int) -> float | None:
    return round(hit / total, 3) if total else None


def stats(store: Store) -> dict:
    """Aggregates over graded attempts: trend, miss rates, calibration, time."""
    rows = []
    miss = defaultdict(lambda: [0, 0])
    miss_lang = defaultdict(lambda: [0, 0])
    for sub in store.submissions():
        view = attempt_view(store, sub)
        if view is None or view["feedback"] is None:
            continue
        rows.append((sub, view))
        lang = view["problem"]["language"]
        for issue in view["key"]["issues"]:
            missed = issue["id"] in view["result"]["missed"]
            miss[issue["category"]][0] += missed
            miss[issue["category"]][1] += 1
            miss_lang[lang][0] += missed
            miss_lang[lang][1] += 1
    rows.sort(key=lambda r: r[0].submitted_at)

    calib = defaultdict(lambda: [0, 0])
    time = defaultdict(lambda: [0.0, 0])
    by_source = defaultdict(list)
    for sub, view in rows:
        calib[sub.confidence][0] += view["result"]["verdict_credit"] == 1.0
        calib[sub.confidence][1] += 1
        time[view["problem"]["difficulty"]][0] += sub.elapsed_seconds / view["problem"]["target_seconds"]
        time[view["problem"]["difficulty"]][1] += 1
        by_source[view["problem"]["source"]["kind"]].append(view["result"]["score"])

    return {
        "graded": len(rows),
        "trend": [{"attempt_id": s.attempt_id, "score": v["result"]["score"]} for s, v in rows[-20:]],
        "miss_rate_by_category": {k: _rate(*v) for k, v in miss.items()},
        "miss_rate_by_language": {k: _rate(*v) for k, v in miss_lang.items()},
        "verdict_right_by_confidence": {str(k): _rate(*v) for k, v in sorted(calib.items())},
        "time_vs_target_by_difficulty": {k: round(t / n, 3) for k, (t, n) in time.items()},
        "avg_score_by_source": {k: round(sum(v) / len(v), 1) for k, v in by_source.items()},
    }
