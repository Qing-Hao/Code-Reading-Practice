# Review Drill design

## Problem statement

AI makes code cheap to generate, so review becomes the bottleneck, and accountability for what ships
stays with the reviewer. Review Drill trains one skill: review code against its intent, spot what is
wrong, know how sure you are, and decide ship, fix or ask, quickly and accountably.

## Architecture

```
Browser (web/)  <--HTTP + SSE-->  FastAPI (app/main.py)  <--files-->  data/
                                         ^                              ^
                                    watchfiles                     Claude Code
                                  (app/events.py)          (/grade, /generate, ... via app/cli.py)
```

- All state is JSON files under `data/`. Claude Code reads and writes them; nothing calls an LLM API.
- The server watches `data/`. A new or changed file in `feedback/` pushes a `feedback` event; a change in
  `problems/` or `keys/` pushes a `problems` event. The browser refetches on each event.
- Unfinished drafts (comments, verdict, elapsed time) live in the browser's localStorage.
- `app/cli.py` gives Claude Code a grading bundle and a validator, so a malformed feedback file is caught
  before the UI shows it. The UI also reports a feedback file that fails validation.

| Folder | Written by | Committed |
| --- | --- | --- |
| `data/problems/<id>.json` | `/generate`, `/import-real` | yes |
| `data/keys/<id>.json` | `/generate`, `/import-real`, `/dispute` | yes |
| `data/submissions/<attempt>.json` | the server on submit | no (personal history) |
| `data/feedback/<attempt>.json` | `/grade`, `/recap`, `/dispute` | no |

Schemas are the pydantic models in `app/models.py`. Line numbers are 1-based display rows; for diffs,
each row of the diff (including `-` rows) counts.

## Scoring (`app/scoring.py`)

A comment **hits** a key issue when it is in the same file and within the issue's line range ±1.
An exact range match beats a tolerance match, and the narrowest range wins.

When Claude's feedback arrives, a hit graded quality 0 ("not about this issue") becomes a false alarm.
The deterministic layer places the comment and Claude confirms it is about the right thing.

| Part | Weight | How |
| --- | --- | --- |
| Issues found | 45% | severity-weighted recall (low 0.5, medium 1, high 2, critical 3); 100% on clean code |
| Flags that were real | 15% | hits / comments; 100% with no comments |
| Comment quality | 15% | Claude's 0–2 grade averaged over hits |
| Speed | 10% | min(1, target / time) × accuracy, so skimming does not pay |
| Verdict | 15% | credit table below |

Verdict credit (expected → yours): approve → approve 1, nits 0.75, ask 0.25; nits → nits 1, approve 0.75,
changes 0.5, ask 0.25; changes → changes 1, ask 0.5; ask → ask 1, changes 0.5. Everything else is 0.
Approving code whose key says `changes` caps the score at 30.

Confidence is not scored. It feeds calibration stats: how often your verdict is right at each confidence level.

## Problem sources

- **Generated**: written by `/generate`, about 20% clean and 10% nits-only, with spec mismatches as a
  first-class issue type.
- **Real**: from bug-fix commits (BugsInPy, CVEfixes, GitHub). The code is taken from the buggy commit and
  the key from the fix. `source` records repo, fix commit URL, buggy sha, dataset, license and date.
- The source badge is hidden until you submit by default, because real bug-fix problems always contain a
  bug. The header setting can show it always.

## Decisions

- File drop + watcher + SSE rather than an MCP server: the simplest option for Claude Code, since it
  already writes files. Revisit if malformed files become common.
- The answer key is shown right after submit (a preliminary score); Claude's grading only adds comment
  quality, a summary and corrections.
- The timer pauses when the browser tab is hidden or you switch to History/Stats.
