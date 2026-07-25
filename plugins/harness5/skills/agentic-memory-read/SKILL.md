---
name: agentic-memory-read
description: >
  Use at the START of any task-execution session, or whenever picking up interrupted work,
  opening an epic to check on its children, or descending into a child ticket mid-session, to
  load ambient progress-state (blockers, drift, gotchas, where the last session left off)
  before touching code. Backed by a remote Graphiti temporal knowledge graph via the `memory`
  MCP server. Trigger on cold start, resuming a backlog ticket/epic, or picking up any work
  that a prior (possibly context-limited) session may have partially completed.
---

# agentic-memory-read (Graphiti)

Loads **ambient progress-state** — not prior "decisions" — so a cold-started session (yours or
someone else's) knows where the last session left off: blockers, drift between ticket intent
and delivered result, gotchas, and where to pick up. Backed by a self-hosted Graphiti +
FalkorDB stack — the `graphiti-mcp` service in `infrastructure/docker-compose.yml`, with
entity-type schema at `infrastructure/config.yaml` — exposed as the `memory` MCP server.

Tool names and signatures below are **verified against the live upstream source**
(`getzep/graphiti`, `mcp_server/src/graphiti_mcp_server.py`, main branch, checked
2026-07-10) — keep them accurate, don't invent params.

## Scope resolution

Memory is scoped to the GitHub work hierarchy, project-namespaced (the infra is shared across
projects):

- **Project scope** — `owner_repo`. Derive from the git remote: `gh repo view --json
  nameWithOwner -q .nameWithOwner`, or parse `git remote get-url origin` if `gh` isn't
  available.
- **Epic/ticket scope** — `owner_repo_<issue>`. Append the issue number resolved from (in
  order of preference) the current branch name, the open PR for the branch, or the task brief
  you were given.

These scope keys are used directly as the Graphiti `group_id`, underscore-joined — not
`owner/repo` or `owner/repo#<issue>`, and not dash-joined either. This convention went through
two rounds of live verification against the `mem-graphiti-mcp` container
(zepai/knowledge-graph-mcp, FalkorDB-backed):

1. **2026-07-14, round 1** — slash/hash-joined group_ids (e.g. `oolio-group/oolio-one-gitops`
   or `oolio-group/oolio-one-gitops#424`) make FalkorDB's RediSearch full-text index throw
   `RediSearch: Syntax error at offset 17 near oolio` on group_ids containing `/` or `#`. Only
   `search_nodes`/`search_memory_facts` surface that error directly — `get_episodes` silently
   returns empty for the same group_id instead, so the failure mode is easy to miss. The fix
   at the time was to switch to dash-joined (`owner-repo`, `owner-repo-<issue>`).
2. **2026-07-14, round 2** — dash-joined group_ids turned out to trip the **same class** of
   RediSearch syntax error, and worse: on group_id `tillpos-tony-my-claude`, the write didn't
   fail cleanly — it hung indefinitely, retrying every extracted keyword combination forever
   during Graphiti's internal entity-dedup search, with `count(n)` stuck at 0 in FalkorDB for
   5+ minutes and no episode ever persisted. A control test with an **underscore-joined**
   group_id (`tillpos_tony_my_claude_test`) completed the full pipeline cleanly — LLM
   extraction, embeddings, edge resolution, `Successfully processed episode` logged, 6
   entities persisted, zero RediSearch errors.

Use the underscore-joined form always; both this skill and `agentic-memory-write` must stay
consistent.

## Read model: read wide (downward only), write narrow

Reads widen *downward* into child tickets of whatever scope you're cold-starting into — never
upward into parents. An orphan ticket's memory shouldn't leak epic-level notes, and the
reverse isn't needed because writes always go to the most-specific scope (see
`agentic-memory-write`).

1. **Ticket cold-start** (you're picking up a specific issue): query only that ticket's
   scope — `group_ids=["owner_repo_<issue>"]`. This is the common case.
2. **Epic cold-start** (you're opening a parent epic to see where its children stand):
   enumerate child sub-issues live via `gh` (e.g. `gh issue view <epic> --json ...` / the
   sub-issue listing for that issue), then query `group_ids=[epic, ...children]`. Pull only a
   **bounded per-child summary** — recent status, open blockers, open drift — not the full raw
   episode history for every child. Fetch a specific child's raw detail on demand only when
   you actually descend into working that child ticket.
3. **Project cold-start** (no specific issue — ad-hoc/orphan work, or scanning what's active):
   query your own project-scope notes (`owner_repo`) plus a bounded index of active epics.
   Never recursively dump every epic's every child — that defeats "bounded."

## Read-time reconciliation

Memory is not authoritative — cross-check against live GitHub state before trusting a note:

- Check the open/closed status of the scope's issue(s) (e.g. `gh issue view <n> --json
  state`).
- Treat memory tied to a **CLOSED** ticket as historical context, not current state — the work
  may have shipped, or the note may predate a resolution that never made it back into memory.
  Live ticket status is the tiebreaker, not the memory note.

## Tools

Primary read is **scope + recency**, not semantic search:

- `get_episodes(group_ids=[...], last_n=<n>)`: the default read — recent raw episodes for the
  resolved scope(s). Start here.
- `search_memory_facts(query=<topic>, group_ids=[...])`: scope+recency search over extracted
  facts (edges) when you need something more targeted than "most recent."
- `search_nodes(query=<topic>, group_ids=[...])`: SECONDARY — semantic entity search. Use when
  scope+recency reads don't surface what you need, not as the first call.
- `get_status()`: confirm the server + database connection are healthy before assuming a read
  silently failed (or returned stale/empty results).

## MCP client registration

This repo doesn't track a committed MCP client-config file, so registration happens in your
own Claude Code MCP settings (not part of this PR). Point it at the compose stack's HTTP
endpoint (default host port from `infrastructure/.env.example` is `8121`, overridable):

```json
{
  "mcpServers": {
    "memory": {
      "type": "http",
      "url": "http://localhost:8121/mcp/"
    }
  }
}
```

Note the trailing `/mcp/` and `"http"` transport — verified against the upstream server's
default transport (SSE is listed as deprecated upstream, not the recommended path used here).

## Next step

Once you've loaded progress-state and done the work, use the `agentic-memory-write` skill to
record a blocker, drift, stopping point, silent descope, or resolution before ending the
session.
