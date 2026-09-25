---
description: Grade submitted reviews and push feedback to the Review Drill UI
argument-hint: "[attempt_id]"
---

Grade the user's code review attempt(s) in Review Drill.

1. Get the grading bundle:
   - With an argument: `uv run python -m app.cli show $ARGUMENTS`
   - Without: `uv run python -m app.cli pending`
   The bundle has the spec, the code with line numbers, the answer key, and each user comment
   already matched to a key issue (`HIT kN`) or marked `FALSE ALARM` by the deterministic scorer
   (±1 line tolerance).

2. Grade every comment with a `quality` from 0 to 2 and a short `note` (1–2 sentences, direct, no praise padding):
   - **0**: the comment is not really about the issue it landed near, or it is wrong. A HIT graded 0
     is turned into a false alarm by the scorer, so use 0 when the line matched by accident.
   - **1**: right issue, but the cause is vague or the suggested fix would not work.
   - **2**: names the concrete failure and a fix that would work.
   For `FALSE ALARM` comments, quality is ignored; the note explains why the code is fine here.
   If a false alarm is actually a real problem the key missed, say so in the note and suggest `/dispute`.

3. Write a `summary` of 2–4 sentences: what they caught, what they missed and the reading habit that
   would have caught it, and one line on confidence calibration if it was off (sure and wrong, or unsure and right).

4. Write the file with the Write tool in one go to the path the bundle prints
   (`data/feedback/<attempt_id>.json`), using the template's shape:
   `{"attempt_id", "graded_at", "comments": [{"comment_id", "quality", "note"}], "summary"}`.
   Grade every comment id exactly once.

5. Validate: `uv run python -m app.cli validate data/feedback/<attempt_id>.json`. Fix and rewrite until it passes.
   The browser updates on its own once the file is valid.

6. In the terminal, give a 2–3 line recap and invite questions. The user may discuss the review here;
   answer as a senior reviewer would. When they are done, they run `/recap`.
