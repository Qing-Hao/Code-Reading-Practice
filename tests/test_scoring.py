from app.models import Feedback
from app.scoring import BAD_APPROVAL_CAP, calibration_label, match_comments, score
from tests.conftest import make_sub

ORDERS = "orders/queries.py"


def feedback_for(sub, quality=2):
    return Feedback(attempt_id=sub.attempt_id, graded_at="x", summary="s",
                    comments=[{"comment_id": c.id, "quality": quality, "note": "n"} for c in sub.comments])


def test_perfect_review_scores_100(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    sub = make_sub(p.id, [(ORDERS, 3, "off by one"), (ORDERS, 4, "injection"), (ORDERS, 8, "n+1")], elapsed=120)
    r = score(p, k, sub, feedback_for(sub))
    assert r["found"] == ["k1", "k2", "k3"] and r["missed"] == []
    assert r["recall"] == 1 and r["precision"] == 1 and r["quality"] == 1
    assert r["score"] == 100
    assert r["calibration"] == "sure-right"


def test_score_pending_until_feedback(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    r = score(p, k, make_sub(p.id, [(ORDERS, 4, "injection")]))
    assert r["score"] is None and r["quality"] is None
    assert r["found"] == ["k2"]


def test_line_tolerance_is_one(store):
    k = store.key("py-orders-pagination")
    m = match_comments(make_sub("py-orders-pagination", [(ORDERS, 2, "a"), (ORDERS, 11, "b"), (ORDERS, 12, "c")]), k)
    assert m["matches"] == {"c1": "k1", "c2": "k3", "c3": None}


def test_exact_and_narrowest_range_wins(store):
    k = store.key("sql-monthly-revenue")
    m = match_comments(make_sub("sql-monthly-revenue", [("reports/monthly_revenue.sql", 7, "12 months")]), k)
    assert m["matches"]["c1"] == "k3"


def test_other_file_same_line_does_not_match(store):
    k = store.key("js-checkout-retry")
    m = match_comments(make_sub("js-checkout-retry", [("api/checkout.js", 14, "x"), ("lib/payments.js", 14, "y")]), k)
    assert m["matches"] == {"c1": None, "c2": "k2"}


def test_clean_problem_correct_approve(store):
    p, k = store.problem("py-retry-backoff"), store.key("py-retry-backoff")
    sub = make_sub(p.id, [], verdict="approve", confidence=2, elapsed=100)
    r = score(p, k, sub, feedback_for(sub))
    assert r["recall"] == 1 and r["precision"] == 1 and r["quality"] == 1 and r["verdict_credit"] == 1
    assert r["score"] == 100


def test_false_alarm_on_clean_code_costs_precision(store):
    p, k = store.problem("py-retry-backoff"), store.key("py-retry-backoff")
    sub = make_sub(p.id, [("infra/retry.py", 5, "bad")], verdict="nits")
    r = score(p, k, sub, feedback_for(sub))
    assert r["precision"] == 0 and r["verdict_credit"] == 0.75


def test_approving_broken_code_is_capped(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    sub = make_sub(p.id, [(ORDERS, 3, "a"), (ORDERS, 4, "b"), (ORDERS, 8, "c")], verdict="approve")
    r = score(p, k, sub, feedback_for(sub))
    assert r["bad_approval"] and r["score"] == BAD_APPROVAL_CAP


def test_speed_does_not_reward_skimming(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    sub = make_sub(p.id, [(ORDERS, 16, "nothing")], elapsed=5)
    r = score(p, k, sub, feedback_for(sub))
    assert r["raw_speed"] == 1 and r["speed"] == 0


def test_verdict_credit_matrix(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    assert score(p, k, make_sub(p.id, [], verdict="ask"))["verdict_credit"] == 0.5
    assert score(p, k, make_sub(p.id, [], verdict="nits"))["verdict_credit"] == 0
    nits_p, nits_k = store.problem("ts-format-price"), store.key("ts-format-price")
    assert score(nits_p, nits_k, make_sub(nits_p.id, [], verdict="approve"))["verdict_credit"] == 0.75


def test_severity_weighting(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    r = score(p, k, make_sub(p.id, [(ORDERS, 4, "injection")]))
    assert r["found_weight"] == 3 and r["total_weight"] == 6 and r["recall"] == 0.5


def test_zero_quality_turns_nearby_hit_into_false_alarm(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    sub = make_sub(p.id, [(ORDERS, 4, "injection"), (ORDERS, 5, "fetchall loads everything")])
    assert score(p, k, sub)["matches"] == {"c1": "k2", "c2": "k2"}
    fb = Feedback(attempt_id=sub.attempt_id, graded_at="x", summary="s", comments=[
        {"comment_id": "c1", "quality": 2, "note": "n"}, {"comment_id": "c2", "quality": 0, "note": "unrelated"}])
    r = score(p, k, sub, fb)
    assert r["matches"] == {"c1": "k2", "c2": None}
    assert r["precision"] == 0.5 and r["quality"] == 1


def test_ungraded_near_miss_does_not_count_as_found(store):
    p, k = store.problem("py-orders-pagination"), store.key("py-orders-pagination")
    sub = make_sub(p.id, [(ORDERS, 3, "a"), (ORDERS, 4, "b")])
    fb = Feedback(attempt_id=sub.attempt_id, graded_at="x", summary="s", comments=[{"comment_id": "c1", "quality": 2, "note": "n"}])
    r = score(p, k, sub, fb)
    assert r["found"] == ["k1"] and r["missed"] == ["k2", "k3"]


def test_calibration_labels():
    assert calibration_label(3, 0) == "overconfident"
    assert calibration_label(1, 1.0) == "unsure-right"
    assert calibration_label(1, 0.5) == "unsure-wrong"
    assert calibration_label(2, 1.0) == "medium-right"
