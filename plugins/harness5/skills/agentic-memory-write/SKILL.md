---
name: agentic-memory-write
description: >
  Use whenever you hit a blocker, discover drift between ticket intent and delivered result,
  reach a stopping point (session end, context-limit handoff, done-pending-verification),
  silently descope something, or resolve a previously-noted blocker/drift, to persist that
  ambient progress-state for the next cold start. Backed by a remote Graphiti temporal
  knowledge graph via the `memory` MCP server. Event-driven — not continuous per-step logging,
  not session-end-only.
---

# agentic-memory-write (Graphiti)

Persists **ambient progress-state** — a standup note to the next developer — so a later cold
start (yours or someone else's) can pick up smoothly. This is not a decision log: no
`Decision`/`Outcome` typed shape, no schema file. Backed by the same self-hosted Graphiti +
FalkorDB stack as `agentic-memory-read`, exposed as the `memory` MCP server.

Tool names and signatures below are **verified against the live upstream source**
(`getzep/graphiti`, `mcp_server/src/graphiti_mcp_server.py`, main branch, checked
2026-07-10) — keep them accurate, don't invent params.

## When to write (event-driven, not continuous)

Write at these events only — not on every step, and not only at session end:

- **Blocker** — you're stuck (external dependency, missing access, failing infra, etc.).
- **Drift** — what you delivered doesn't fully match ticket intent (partial completion, an
  interpretation that diverged, etc.).
- **Stopping point** — session end, context-limit handoff, or "done pending human
  verification."
- **Silent descope** — you quietly dropped or deferred part of the ask without it being
  reflected in the ticket.
- **Resolution** — a previously-noted blocker or drift is now cleared. This is a first-class
  event, not an afterthought — see "Resolution as event" below.

## Content model: standup prose, coverage not schema

Don't force a rigid field template. Write natural prose that lets the next reader answer, for
whatever applies:

- **Where does it stand** — what's actually done vs. ticket intent.
- **What's the catch** — the blocker, drift, or gotcha, if any.
- **Where to pick up** — branch, PR, file, or next concrete step.

Include only what's relevant — a pure blocker note doesn't need a full "where it stands"
essay; a clean resolution doesn't need to restate the whole ticket.

### Examples (deliberately different shapes)

**Blocker:**

> Ticket #78: implementation done, but can't verify against staging — staging API is
> returning 500s on the endpoint this depends on. Not our bug; filed with infra. Picking back
> up once staging is healthy again.

**Drift at a stopping point:**

> Ticket #142: ~78% done — the core migration path works and is tested. The remaining 22%
> (backfill for archived records) turned out to need a schema change I didn't want to make
> unreviewed, so I left it out. Ticket should probably stay open or get a follow-up filed;
> code is on `feat/142-migration`, PR #150 (draft).

**Silent descope / gotcha:**

> Ticket #96: shipped without the CSV export the ticket mentions — the existing export lib
> doesn't support the requested column set, and adding that felt out of scope for this
> ticket. Didn't call this out in the PR description; flagging here in case someone expects
> it.

## Write scope

Write to your **most-specific** scope:

- On a ticket → `owner_repo_<issue>` (that ticket).
- Genuinely cross-ticket note (affects the whole epic, not one child) → the epic scope,
  `owner_repo_<epic>`.
- Orphan/ad-hoc work with no issue → project scope, `owner_repo`.

`group_id` must be underscore-joined, not slash/hash-joined and not dash-joined either.
Slash/hash-joining makes FalkorDB's RediSearch full-text index throw `RediSearch: Syntax
error at offset 17 near oolio` on group_ids containing `/` or `#` (confirmed 2026-07-14). A
first fix moved to dash-joining, but that same day, live testing found dash-joined group_ids
trip the same class of RediSearch error and hang the write indefinitely instead of failing
cleanly — reproduced on `tillpos-tony-my-claude`, which never completed (`count(n)` stuck at 0
for 5+ minutes). Underscore-joined (`tillpos_tony_my_claude_test`) completed cleanly with zero
RediSearch errors, so underscore is the verified-safe separator, not just another guess. See
`agentic-memory-read`'s "Scope resolution" section for the full verification detail; keep the
two skills' conventions identical.

Don't write epic-level notes for single-ticket concerns — that breaks read-wide/write-narrow
and pollutes every sibling ticket's epic-level read.

## Resolution as event

When a blocker clears or drifted work gets finished, write a new episode that **names what it
resolves**, e.g.:

> Blocker on #78 noted 2026-07-09 is cleared: staging was misconfigured (wrong env var),
> infra fixed it. Verified against staging now, all green.

Naming the prior state explicitly gives Graphiti's bi-temporal extraction what it needs to
recognize the contradiction and age out (invalidate, not delete) the stale note — don't rely
on a terse "fixed" with no reference to what it fixes.

## `add_memory` call

- `name`: a short episode title, e.g. `"Blocker: #78 staging 500s"` or `"Resolved: #78
  staging blocker"`.
- `group_id`: the single, explicit resolved scope (see "Write scope" above) — never rely on
  the server's configured default (`GRAPHITI_GROUP_ID`, `main`).
- `reference_time`: ISO-8601 (e.g. `2026-07-11T14:30:00Z`) — when the event actually
  happened, not just when you happened to write it.
- `episode_body`: the prose note itself (see examples above).
- `source`: `"text"` (default) unless feeding structured JSON, in which case `"json"` with a
  properly-escaped JSON string.

## Other write/delete tools

- `delete_episode(uuid=...)` / `delete_entity_edge(uuid=...)`: remove a mistaken write.
  Cascade behavior is scoped to what that episode/edge solely created — check the tool's own
  docstring before relying on it for a large mistake.

## Rules

- Memory is **non-authoritative** and never substitutes for ticket/ADR hygiene: if a fact
  should update or close the ticket, update the ticket; a real architectural decision still
  goes to an ADR. Memory is the tacit catch-net for what falls between those — the small
  stuff that evaporates today.
- Never store secrets, tokens, or credentials in memory episodes.
- Event-driven: not continuous (don't log every step) and not session-end-only (write
  blockers/drift/resolutions as they happen).

## Loading context first

If you haven't already loaded progress-state for this scope this session, use the
`agentic-memory-read` skill first.

## Relationship to file-based memory

If the current work is scoped to a GitHub issue/PR (not ad-hoc/no-ticket work), prefer this
skill over writing to the generic per-project `memory/*.md` auto-memory files for
progress-state, blockers, or drift. Those files are for durable facts about the user, project,
or feedback that outlive a single ticket; this skill is the ticket-scoped ambient catch-net —
use it whenever a stopping point, blocker, drift, or resolution falls inside a ticket's scope.
