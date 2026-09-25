---
description: Import real bugs from open-source fix commits as Review Drill problems
argument-hint: "[count] [python|sql|typescript|javascript] [bugsinpy|cvefixes|github]"
---

Turn real bug-fix commits into practice problems. Arguments: `$ARGUMENTS` (count default 2).

## Sources

- **BugsInPy** (Python): `https://raw.githubusercontent.com/soarsmu/BugsInPy/master/projects/<project>/bugs/<n>/bug.info`
  gives `buggy_commit_id` and `fixed_commit_id`. Projects list: `projects/` in that repo.
- **CVEfixes** (security, many languages): pick a CVE fix commit from a project with a permissive license.
- **GitHub** (SQL, TS/JS): merged PRs or commits in popular repos whose message says it fixes a bug
  ("fix", "regression", "revert"), especially migration and query fixes for SQL.

Skip anything already imported (check `source.ref` in `data/problems/*.json`).

## Steps per problem

1. Fetch the fix diff (`https://github.com/<owner>/<repo>/commit/<fix_sha>.diff`) and the commit message and date
   (`https://api.github.com/repos/<owner>/<repo>/commits/<fix_sha>`).
2. Fetch the file(s) at the buggy commit (`https://raw.githubusercontent.com/<owner>/<repo>/<buggy_sha>/<path>`).
   Check the repo license and only use permissive ones (MIT, BSD, Apache-2.0). Record it.
3. Trim to the relevant function(s) with enough context to judge, 10–80 lines. Do not edit the code itself.
4. Write the **spec** from the intent (the issue or PR that introduced the code), never from the fix. The spec
   must not give the bug away.
5. Build the key from the fix diff: one issue per real defect, lines mapped onto the trimmed snippet. Ignore
   pure refactors, tests and formatting in the fix. If the fix is ambiguous, skip this commit.
6. Write `data/keys/<id>.json` then `data/problems/<id>.json` (same schema as `/generate`) with id
   `real-<project>-<slug>` and
   `"source": {"kind": "real", "repo": "<owner>/<repo>", "ref": "<fix commit URL>", "sha": "<short buggy sha>",
   "dataset": "BugsInPy (<project> bug <n>)" or similar, "license": "<license>", "date": "<fix commit date>",
   "notes": "Code at buggy commit ...; key from fix commit ..."}`.
7. Validate: `uv run python -m app.cli validate data/problems/<id>.json data/keys/<id>.json`.

Do not reveal the bugs in the terminal. Reply with the new problem ids and their sources only.
