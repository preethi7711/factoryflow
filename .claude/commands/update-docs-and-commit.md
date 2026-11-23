---
description: Update status, changelog and architecture docs for the work just done, then commit
argument-hint: [short milestone name]
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Read, Edit, Write
---

You are closing a milestone: **$ARGUMENTS**

## Context
- Status: !`git status --short`
- Changes since last commit: !`git diff HEAD --stat`
- Recent commits: !`git log --oneline -10`

## Steps
1. Read the diff (`git diff HEAD`) and work out what actually changed. Do not guess from file names.
2. Update **only what changed**:
   - `docs/project_status.md`: set the date to today, move finished items to *Done*, refresh *Next*,
     update the benchmark scoreboard (B1–B13) from the latest test run if tests were run.
   - `docs/changelog.md`: add bullets under `[Unreleased]` (Added / Changed / Fixed / Removed).
   - `docs/architecture.md`: only if a module boundary, table, invariant mechanism or dependency changed.
   - `CLAUDE.md` *Commands* block: only if a command became real or changed.
   - Never edit `docs/PROBLEM.md`.
3. Don't duplicate content between docs. Link instead.
4. If any test was run and failed, **stop**: report it and don't commit.
5. Make sure nothing secret is staged (`.env`, keys, tokens). If something is, stop and warn.
6. Stage the docs together with the related code changes and commit with a Conventional Commit message
   (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`). Use one commit per logical change.
   Split the commit if the diff mixes concerns. End each message with the project's co-author line.
7. Do **not** push. Print the new `git log --oneline -5` and a 3-line summary.
