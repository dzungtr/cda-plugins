# 3. Agentic memory is ambient progress-state, not a decision store

Date: 2026-07-11

## Status

Accepted

## Context

An earlier iteration originally built the `memory` MCP server layer (Graphiti + FalkorDB,
`infrastructure/config.yaml`) as a **decision manager**: a `Decision`/`Outcome` entity schema
(`skills/agentic-memory-write/schema.py`) with a `SUPERSEDES` edge type, registered as custom
`entity_types`/`edge_types`/`edge_type_map` in `infrastructure/config.yaml`, retrieved primarily
via semantic search (`search_nodes`).

A grilling/design session surfaced that this framing solves the wrong problem. The actual gap: a
long-running agent frequently finishes work that only *partially* matches its ticket — say 78%
done, with the remainder blocked, drifted from ticket intent, or pending human verification. The
ticket stays open, but the next session (possibly a different agent entirely, since the prior
session is context-limited and can't be resumed) cold-starts with no idea what happened. Today a
human manually reconstructs this state by re-reading code, diffs, and PR comments. The verbose,
sub-ticket reality — blockers, drift, gotchas, silent descopes — never lands in a ticket and
evaporates.

A decision-manager schema doesn't address this: decisions are relatively rare and already have a
home (ADRs); what's actually missing is a place for the *tacit, in-flight* state that's too
granular for a ticket and too undecided to be an ADR.

## Decision

**Reframe the layer as ambient progress-state memory** — a self-service, agent-initiated store of
tacit progress state, keyed to the GitHub work hierarchy, that makes cold-start handover smooth.
It is explicitly **non-authoritative**: a catch-net beside the ticket system, never a replacement.
The process still works without it; with it, any agent can ask "what's the state of this epic /
where do I pick up?" and get an answer.

Concretely:

1. **Not a decision-manager.** Drop the `Decision`/`Outcome` entity types, the `SUPERSEDES` edge
   type, `edge_type_map`, and `schema.py` entirely. `config.yaml` now registers only Graphiti's
   upstream built-in entity types (Preference, Requirement, Procedure, Location, Event,
   Organization, Document, Topic, Person, Object). Retire the "G1/G2/G3 decision-drift" framing
   from the original spec.
2. **Substrate: keep Graphiti (Path A).** No infra change. Primary read is **scope + recency**
   (`get_episodes` / `search_memory_facts` filtered by `group_ids`), not semantic search;
   `search_nodes` becomes secondary. Bi-temporal invalidation is kept and is now the mechanism for
   aging out resolved blockers/drift (see "Resolution as event" in
   `skills/agentic-memory-write/SKILL.md`), not for superseding decisions.
3. **Scope-key model.** Memory is scoped to the GitHub work hierarchy, project-namespaced (the
   memory infra is shared across projects): `owner/repo` (project) · `owner/repo#<parent>` (epic)
   · `owner/repo#<sub-issue>` (ticket) — resolved deterministically from the git remote plus
   branch/PR/task-brief, used directly as the Graphiti `group_id`. Readable form now; rename
   fragility is an accepted trade-off. Not revisited in this ADR: rename-proof node-ID scope keys.
4. **Write narrow, read wide (downward).** Writes always go to the most-specific scope (usually a
   single ticket). Reads widen downward only: a ticket cold-start queries just that ticket; an
   epic cold-start enumerates child sub-issues live via `gh` and queries the epic plus all
   children, but pulls only bounded per-child summaries, fetching raw detail on demand when
   descending into a specific child; a project cold-start reads its own ad-hoc notes plus a bounded
   index of active epics — never a recursive dump of everything.
5. **Writes are event-driven**, not continuous and not session-end-only: blocker, drift, stopping
   point, silent descope, and resolution. Content is standup-prose to the next developer —
   coverage of "where it stands / what's the catch / where to pick up," not a rigid field schema.
6. **Staleness** relies on resolution being a first-class write event (a superseding note that
   names what it resolves, letting Graphiti's bi-temporal extraction age out the stale state) plus
   read-time reconciliation against live GitHub issue open/closed status. An automated
   GitHub-events ingester is deferred.
7. **Three homes, one boundary:** ADR (architectural *why*) / GitHub Issues (*what/whether*,
   system of record) / Memory (tacit catch-net, non-authoritative). Memory never substitutes for
   ticket or ADR hygiene — if a fact should update or close a ticket, update the ticket; a real
   architectural decision still goes to an ADR.

## Consequences

- `skills/agentic-memory-read/SKILL.md` and `skills/agentic-memory-write/SKILL.md` are rewritten
  around scope resolution, read-wide/write-narrow, and event-driven standup-prose writes instead
  of decision/outcome capture.
- `skills/agentic-memory-write/schema.py` is deleted; no code in this repo models a typed
  Decision/Outcome entity.
- `infrastructure/config.yaml` no longer registers `Decision`, `Outcome`, or `SUPERSEDES`; only
  Graphiti's upstream built-in entity types are active. `docker-compose.yml`, `.env.example`, and
  the LLM/embedder/database/server sections of `config.yaml` are unaffected by this ADR — the
  embedder-endpoint decoupling from an earlier fix stays intact.
- Any future consumer of this memory layer should scope reads/writes by `owner/repo[#issue]`, not
  by ad-hoc `proj:<slug>` strings from the earlier framing.

## Measured results

_(Left empty — filled in at initiative close, per this repo's design-session convention.)_
