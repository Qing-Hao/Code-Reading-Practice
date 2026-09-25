# Review Drill

A local app for practicing code review: read code fast against a spec, flag what is wrong,
decide ship / fix / ask, and say how sure you are. Claude Code generates problems and grades
your reviews; the browser updates live when it does. No API key needed.

## Run

```powershell
uv sync
uv run uvicorn app.main:app --port 8765
```

Open http://localhost:8765 and keep a Claude Code session open in this folder.

## The loop

1. Pick a problem from the queue. Read the spec, then the code. The timer runs while you review.
2. Click a line number to comment. Pick a verdict (Approve, Approve with nits, Request changes,
   Can't judge yet) and a confidence, then submit. The timer stops and you see the answer key at once.
3. In Claude Code run `/grade`. Claude grades each comment and writes a summary; the page updates on its own.
4. Ask follow-up questions in the terminal. Run `/recap` to save the takeaways to the attempt,
   or `/dispute` if you think the answer key is wrong.

## Slash commands

| Command | What it does |
| --- | --- |
| `/grade [attempt_id]` | Grade ungraded attempts (or one) and push feedback to the UI |
| `/generate <lang> <difficulty> [count] [format] [weak] [real=N]` | Create new problems; `weak` targets your worst miss rates; `real=N` makes N of them real bugs |
| `/import-real [count] [lang] [source]` | Turn real bug-fix commits (BugsInPy, CVEfixes, GitHub) into problems |
| `/recap [attempt_id]` | Save a summary of the terminal discussion to the attempt |
| `/dispute [attempt_id] <reason>` | Re-examine the answer key and revise it if it is wrong |

## CLI helpers

```powershell
uv run python -m app.cli pending        # ungraded attempts with key and matches
uv run python -m app.cli show latest    # one attempt with its feedback
uv run python -m app.cli validate       # check every data file
uv run python -m app.cli stats          # miss rates and calibration as JSON
```

## Tests

```powershell
uv run pytest
```

See [docs/DESIGN.md](docs/DESIGN.md) for scoring rules and data formats.
