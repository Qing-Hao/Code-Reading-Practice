"""Command-line helpers that Claude Code's slash commands call to grade and validate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.models import AnswerKey, Feedback, Problem, Submission
from app.scoring import score
from app.stats import stats
from app.store import Store


def _bundle(store: Store, sub: Submission) -> str:
    """Render everything needed to grade one attempt as plain text."""
    problem, key = store.problem(sub.problem_id), store.key(sub.problem_id)
    if problem is None or key is None:
        return f"=== {sub.attempt_id}: problem or key missing ===\n"
    r = score(problem, key, sub, store.feedback(sub.attempt_id))
    out = [f"=== Attempt {sub.attempt_id} ===",
           f"Problem: {problem.id} | {problem.title} | {problem.language} {problem.format} {problem.difficulty} | target {problem.target}s",
           f"Source: {problem.source.kind}" + (f" {problem.source.repo} {problem.source.ref}" if problem.source.kind == "real" else ""),
           f"Spec {problem.spec.id}: {problem.spec.text}",
           f"Context: {problem.context}", ""]
    for f in problem.files:
        out.append(f"--- {f.path} ---")
        for n, row in enumerate(f.rows(), 1):
            out.append(f"{n:4} |{row['kind']} {row['text']}")
        out.append("")
    out.append(f"Answer key verdict: {key.verdict}")
    for i in key.issues:
        out.append(f"  [{i.id}] {i.file}:{i.start}-{i.end} {i.category}/{i.severity} {i.title}: {i.explanation} Fix: {i.fix}")
    out += ["", f"Submission: verdict={sub.verdict} confidence={sub.confidence}/3 elapsed={sub.elapsed_seconds}s"]
    for c in sub.comments:
        hit = r["matches"][c.id]
        out.append(f"  ({c.id}) {c.file}:{c.line} [{c.category}] {c.text!r} -> {'HIT ' + hit if hit else 'FALSE ALARM'}")
    out += [f"Found: {r['found'] or 'none'} | Missed: {r['missed'] or 'none'} | verdict credit {r['verdict_credit']} | calibration {r['calibration']}",
            "", f"Write feedback to: {store.feedback_dir / (sub.attempt_id + '.json')}",
            "Template:",
            json.dumps({
                "attempt_id": sub.attempt_id,
                "graded_at": datetime.now().isoformat(timespec="seconds"),
                "comments": [{"comment_id": c.id, "quality": 0, "note": ""} for c in sub.comments],
                "summary": "",
            }, indent=2), ""]
    return "\n".join(out)


def cmd_pending(store: Store, args) -> int:
    subs = [s for s in store.submissions() if store.feedback(s.attempt_id) is None]
    if args.latest:
        subs = subs[-1:]
    if not subs:
        print("No submissions waiting for grading.")
        return 0
    for s in subs:
        print(_bundle(store, s))
    return 0


def cmd_show(store: Store, args) -> int:
    sub = store.submission(args.attempt_id) if args.attempt_id != "latest" else (store.submissions() or [None])[-1]
    if sub is None:
        print(f"No attempt {args.attempt_id}")
        return 1
    print(_bundle(store, sub))
    fb = store.feedback(sub.attempt_id)
    if fb:
        print("Current feedback:\n" + fb.model_dump_json(indent=2))
    return 0


def _validate_file(store: Store, path: Path) -> list[str]:
    folder = path.parent.name
    text = path.read_text(encoding="utf-8")
    try:
        if folder == "problems":
            Problem.model_validate_json(text)
            return []
        if folder == "keys":
            key = AnswerKey.model_validate_json(text)
            problem = store.problem(key.problem_id)
            return [f"no problem file for {key.problem_id}"] if problem is None else key.check_against(problem)
        if folder == "submissions":
            Submission.model_validate_json(text)
            return []
        if folder == "feedback":
            fb = Feedback.model_validate_json(text)
            sub = store.submission(fb.attempt_id)
            if sub is None:
                return [f"no submission {fb.attempt_id}"]
            if path.stem != fb.attempt_id:
                return [f"file name {path.stem} does not match attempt_id {fb.attempt_id}"]
            ids = {c.id for c in sub.comments}
            graded = {c.comment_id for c in fb.comments}
            errs = [f"unknown comment_id {x}" for x in graded - ids]
            errs += [f"comment {x} not graded" for x in ids - graded]
            return errs
    except ValidationError as e:
        return [str(e)]
    return [f"not in a known data folder: {folder}"]


def cmd_validate(store: Store, args) -> int:
    if args.paths:
        paths = [Path(p) for p in args.paths]
    else:
        paths = []
        for d in (store.problems_dir, store.keys_dir, store.submissions_dir, store.feedback_dir):
            paths += sorted(d.glob("*.json"))
        paths += [store.keys_dir / f"{p.stem}.json" for p in store.problems_dir.glob("*.json")
                  if not (store.keys_dir / f"{p.stem}.json").exists()]
    failed = 0
    for p in paths:
        errs = ["missing file"] if not p.exists() else _validate_file(store, p)
        if errs:
            failed += 1
            print(f"FAIL {p}")
            for e in errs:
                print(f"     {e}")
        else:
            print(f"ok   {p}")
    print(f"{len(paths) - failed}/{len(paths)} valid")
    return 1 if failed else 0


def cmd_stats(store: Store, args) -> int:
    print(json.dumps(stats(store), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Review Drill helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pending", help="print ungraded attempts with key and deterministic matches")
    p.add_argument("--latest", action="store_true", help="only the newest ungraded attempt")
    s = sub.add_parser("show", help="print one attempt (or 'latest') with its current feedback")
    s.add_argument("attempt_id")
    v = sub.add_parser("validate", help="validate data files (all when no paths are given)")
    v.add_argument("paths", nargs="*")
    sub.add_parser("stats", help="print miss rates and calibration as JSON")
    args = parser.parse_args(argv)
    store = Store()
    return {"pending": cmd_pending, "show": cmd_show, "validate": cmd_validate, "stats": cmd_stats}[args.cmd](store, args)


if __name__ == "__main__":
    sys.exit(main())
