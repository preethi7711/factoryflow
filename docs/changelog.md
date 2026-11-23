# Changelog

All notable changes, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Each milestone adds a section. Commit hashes are in `git log`.

## [Unreleased]

### Added
- Phase 0 setup: problem statement (verbatim), `CLAUDE.md`, `.env.example`, `.gitignore`, `.gitattributes`.
- Docs: `project_spec.md` (requirements, tiers, benchmark numbers, assumptions), `architecture.md` (provisional),
  `project_status.md`, this changelog.
- Claude Code slash command `/update-docs-and-commit`.
- Approved plan: `architecture.md` (stack, hosting, ER diagram, invariant mechanisms), `roadmap.md`
  (P1–P11, cut lines, wow list, teaching protocol), spec test logins and assumptions A13–A15, H1.
- Project skills `stock-ledger`, `gst-rules`, `benchmark-check`, and subagent `ledger-auditor`.

### Changed
- A5: opening finished goods valued at standard material cost ₹19.85/pkt.
- Offline order queue moved from stretch into P8 (§4.1 "strongly preferred").
- CLAUDE.md: plain JS frontend, single deployable, hosting, handoff and xfail rules.
