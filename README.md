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

## Remote access (Tailscale)

Use the app from your phone or another laptop while it keeps running on this PC. The app has no
login, so keep it on your private tailnet and never expose it to the public internet.

1. Install Tailscale on this PC and on each device you want to use, and sign in to the same account on all of them.
2. Start the app as usual. It stays bound to `127.0.0.1`:
   ```powershell
   uv run uvicorn app.main:app --port 8765
   ```
3. Share it on the tailnet over HTTPS:
   ```powershell
   tailscale serve --bg 8765
   ```
   `tailscale serve status` prints the URL, e.g. `https://<pc-name>.<tailnet>.ts.net`. Open it on any
   device signed in to Tailscale. Run `tailscale serve reset` to stop sharing.
4. To grade away from the PC, open Claude Code in this folder, start Remote Control (`/remote-control`),
   and run `/grade`, `/recap` and the other commands from the Claude app or claude.ai/code.

Keep the PC awake while you are away (Settings > System > Power > Sleep: Never, when plugged in).
Do not use `tailscale funnel`: it makes the app public.

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
