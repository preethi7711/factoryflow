---
name: benchmark-check
description: Run the section 5 benchmark test suite, map results to checks B1–B13, update the scoreboard in docs/project_status.md, and refuse to call a phase done while anything is red. Use before finishing any phase, before merging to main, and whenever someone asks whether the benchmark passes.
allowed-tools: Bash(docker compose:*), Bash(pytest:*), Bash(git status:*), Bash(git diff:*), Read, Edit
---

# Benchmark check

Expected values: docs/project_spec.md section 4 (the single source of truth). Never change an expected
number to make a test pass. If a number is truly wrong, stop and ask the user, then record the reason in the spec assumptions.

## Steps
1. Run: `docker compose run --rm api pytest -m benchmark -v -rxX` (fall back to `cd backend && pytest -m benchmark -v -rxX` if compose isn't up).
2. Classify each test as **PASS**, **XFAIL** (not built yet), **XPASS** (built but its marker wasn't removed, which strict mode turns into a failure) or **FAIL**.
3. Any **XPASS**: remove that test's `xfail` marker **in the same commit as the code that made it pass**, then re-run.
4. Any **FAIL** on a check that previously passed: it's a regression. Stop all other work and report the failing assertion (expected vs actual).
5. Update the *Benchmark scoreboard* in `docs/project_status.md`: one row per check, with ✅ pass / ⏳ xfail / ❌ fail.
6. Also run the full suite (`pytest -q`). Phase done = full suite green and no unexpected xfail for this phase's checks (see docs/roadmap.md "Done when").

## Report format (keep it short)
```
Benchmark: 11/16 pass · 5 xfail · 0 fail
New passes this phase: B7, B10, B10b, B12, B12b
Regressions: none
```
