# Historical documents

These were accurate at the time they were written and are kept here so
future readers can see the original plans next to what shipped. They
are **not the source of truth** for current behaviour — see
[`../../ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`../../CLAUDE.md`](../../CLAUDE.md), and the runbooks / ADRs under
`docs/` for that.

## What's in here

- `refactoring-2026.md` — the v0.1.0 → v0.2.0 refactoring roadmap.
  All 11 phases shipped; the ADR-worthy follow-ups (sidecar daemon,
  storage abstraction, Entra groups overage, cards.py split,
  server-side auth checks) live in `docs/adr/` and `TODO.md`.
- `features/` — six feature spec docs from the initial v0.1.0
  scaffolding (`unified-search`, `personalization`, `data-quality`,
  `metadata-export`, `data-preview`, `enhanced-lineage`). All six
  features are built; the docs describe the original implementation
  strategy, which has since drifted.
