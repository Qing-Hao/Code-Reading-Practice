---
description: Challenge a Review Drill answer key and revise it if it is wrong
argument-hint: "[attempt_id] <what you think is wrong>"
---

The user thinks the answer key or the grading for an attempt is wrong. Arguments: `$ARGUMENTS`.

1. Load the attempt: `uv run python -m app.cli show <attempt_id>` (or `latest`).
2. Re-examine the code, spec and key on the merits. The key was written by an LLM (or derived from a real
   fix commit) and can be wrong, but do not give in just because the user pushes back. Explain your reasoning
   either way, with concrete inputs that show the behaviour.
3. If the key is wrong:
   - Edit `data/keys/<problem_id>.json`: add the missing issue, fix a line range, change severity or verdict.
     This re-scores every attempt on this problem.
   - Edit `data/feedback/<attempt_id>.json`: update the affected comment grades and notes, append a sentence to
     `summary` saying what changed, and set `"key_revised": true`.
   - Validate both files with `uv run python -m app.cli validate <paths>`.
4. If the key stands, say so plainly and change nothing.
