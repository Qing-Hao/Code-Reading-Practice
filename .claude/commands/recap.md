---
description: Save a recap of the review discussion into the Review Drill UI
argument-hint: "[attempt_id]"
---

Summarize the discussion we just had about a graded review and save it so it shows in the app.

1. Find the attempt: `$ARGUMENTS` if given, otherwise the attempt discussed in this conversation
   (or `uv run python -m app.cli show latest`).
2. Write a recap of 3–6 short sentences: the key takeaways, any rule of thumb worth remembering
   (for example "check what defaults do to arithmetic before reading the query"), and anything that was
   corrected during the discussion.
3. Edit `data/feedback/<attempt_id>.json` and set the `"recap"` field to that text. Leave other fields unchanged.
4. Validate: `uv run python -m app.cli validate data/feedback/<attempt_id>.json`. The browser updates on its own.
