# Harness 5 — Agent operating instructions

This file organises agent instructions around the five pillars of harness infrastructure; every project using harness5 follows this structure.

1. Memory — retrieve durable knowledge and preserve ambient progress-state.
2. Backlog management — keep initiatives and executable work in GitHub Issues.
3. Codebase — isolate changes in worktrees and deliver every unit through a PR.
4. Environment — give agents a short, observable feedback loop for their changes.
5. Agent Observability — use telemetry to improve agent behaviour over time.

## Pillar 1 — Memory

Harness5 provides two complementary forms of memory. RAG memory uses `memsearch` to index `docs/` into the Milvus vector database for decision and constraint searches, including glossary lookups, fact checks, and how-to questions. Temporal memory uses Graphiti through the `memory` MCP server and the `agentic-memory-read` and `agentic-memory-write` skills to preserve ambient progress-state between sessions.

### Memsearch auto-context

At the start of any task, extract the **core subject keywords** from the task description — the main noun-phrase or concept being worked on — and run memsearch if `.memsearch.toml` exists in the current project root.

Keyword extraction examples:

- "Review units against naming convention in ADR 0005" → `naming convention`
- "Write a naming convention ADR from oolio-one/sandbox stacks" → `naming convention`
- "Grill issues #204 & #205 against the domain model" → `domain model`
- "Fix DynamoDB table names to follow ADR 0005" → `DynamoDB naming convention`
- "CiliumNetworkPolicy egress for vouchers-service to NATS" → `CiliumNetworkPolicy egress`
- "How does the secret store work?" → `secret store`

Then run:

```sh
memsearch search "<extracted keywords>" -c <collection from .memsearch.toml> --top-k 5
```

Format the results as a fenced block and use them as orientation before reading any `CONTEXT.md` or `docs/` files. If memsearch errors or returns no results, silently continue — do not halt.

**Review and alignment workflows — never skip memsearch first:**

For any task that involves matching code, PRs, or changes against a domain rule — ADR alignment, code review, compliance checks, convention audits — run memsearch on the rule topic **before** listing files, reading diffs, or building any mapping from titles alone. Titles are often non-obvious: an ADR on ports/adapters, secret injection, or terminal-state enforcement will not surface from a file listing. Memsearch catches the intent that titles miss.

The temptation to list files first and infer coverage from names is a known failure mode. The correct chain for any review/alignment task:

1. `memsearch search "<rule or ADR topic>" -c <collection> --top-k 5` — retrieve indexed knowledge on the domain rule first.
2. Use memsearch results to identify which ADRs, conventions, or constraints apply before reading any code.
3. Then open files, diffs, or PRs with that context already loaded.

**Never-skip rule:** If the task involves matching code against a domain rule (ADR, naming convention, compliance spec, architectural constraint), memsearch on the rule topic is **mandatory** — not optional — even if you believe you already know the rule from session memory.

### Temporal memory

Graphiti memory is ambient progress-state, not a decision store: a self-service, non-authoritative catch-net so a later cold start can pick up smoothly. The `graphiti-mcp` Compose service lives in `plugins/harness5/infrastructure/docker-compose.yml`; its entity-type schema is in `plugins/harness5/infrastructure/config.yaml`, and its environment variables are in `plugins/harness5/infrastructure/.env.example`.

- **Cold-start / picking up work:** before touching code, use the `agentic-memory-read` skill for the resolved scope derived from the git remote plus branch, PR, or task brief. Re-query when descending from an epic into a child ticket mid-session.
- **During work:** use the `agentic-memory-write` skill event-driven — on a blocker, discovered drift, stopping point, silent descope, or resolution of a previously noted blocker or drift. Write standup prose for the next developer: where the work stands, what the catch is, and where to pick up. Do not continuously log every step.
- **Three homes:** ADR (architectural *why*) / GitHub Issues (*what*, system of record) / Memory (tacit catch-net, non-authoritative). Memory never substitutes for ticket or ADR hygiene: update the ticket when its state changes, and record real architectural decisions in ADRs.
- Never write secrets to memory.

## Pillar 2 — Backlog management

GitHub Issues, operated through the `gh` CLI, are the backlog and the system of record for planned work.

- Create one master ticket containing the PRD for each initiative.
- Break the initiative into child tickets that can be implemented and reviewed independently.
- Give every ticket enough implementation detail to execute and explicit acceptance criteria to verify completion.
- For complex work, invoke the `design-session` skill to run the PRD → issues → triage flow.

## Pillar 3 — Codebase

Every PR-bound change runs in an isolated git worktree, executed by a background subagent: the worktree + subagent pair is non-negotiable. It keeps `main` clean, isolates concurrent work, and preserves the main session's context for coordination. The main session only dispatches, reviews, and merges; inline edits, root-workspace edits, and edits without a worktree are forbidden.

### Worktree operations

These rules operationalize the worktree half of that pattern:

- Put every worktree at `<project-root>/.worktrees/<branch>` so `.worktrees/` sits directly under the repository root, never at a global path or in another tool's configuration directory.
- Always compute the absolute path with `$(git rev-parse --show-toplevel)/.worktrees/<branch-name>`; never rely on a CWD-relative worktree path.
- Keep the root workspace on `main` and clean at all times. Make no PR-bound edits there.
- Use `git -C <worktree-path> <command>` for git operations in the worktree.

### PR lifecycle

PR is the smallest unit of work. Start from the `main` workspace, create and check out the task worktree, raise a PR, review and merge it, pull the merged result to `main`, and then clean up the worktree. For branch completion, use `superpowers:finishing-a-development-branch` to verify tests before pushing and opening the PR.

## Pillar 4 — Environment

An agent must be able to spin up its own development environment and get fast feedback on its changes. The agent runs all applicable unit and integration tests before raising a PR.

- For changes that cannot be verified locally, such as Terraform, GitOps, or environment configuration, merge the PR first and apply the change from `main` so the repository remains synchronized with the environment.
- Keep the feedback loop short. The control plane — ArgoCD, CI/CD, or IACM — watches the remote repository and triggers updates after merge; the agent observes the resulting environment change and acts on that feedback.
- Use Docker Compose for local services, browser tools such as Playwright or browser-use for UI feedback, mirrord for testing against remote dependencies, and the control plane for deployment feedback.

## Pillar 5 — Agent Observability

Agent observability supports self-reflection and behaviour improvement over time.

- Coding agents export OpenTelemetry data to the SigNoz backend as established by ADR 0004.
- The `cc-observability` MCP server gives agents queryable access to telemetry, including traces, metrics, and logs.
- Use the `self-improvement` skill to ground reflection in observed telemetry rather than guesses.
- Deliver reflection-driven changes to skills or `CLAUDE.md` as PRs.
