# User-scope instructions (apply to every project)

## Two development workflows

Pick the right workflow before starting any task.

### Workflow A — Quick / one-off task

**Use for:** bugfix, single-file edit, small refactor, config tweak, well-scoped change with clear requirements.

Launch as a **background subagent** that runs autonomously — no upfront design, no human-in-the-loop pauses. The main session reports the agent name and returns control immediately.

**Dispatch sequence:**

1. `Agent` tool call with:
   - `name:` **describe the work, not the role** — use a short verb-phrase that tells you what the agent is doing at a glance: `fix-auth-hook`, `add-dark-mode`, `refactor-drainer`, `write-ingest-tests`. Never use generic names like `executor`, `worker`, `agent`, or `general-purpose`.
   - `subagent_type:` chosen for the tools needed (`general-purpose` for file-editing work)
   - `model:` chosen via the model-selection table below
   - `run_in_background: true` — always
2. Report the agent name and return control. Don't poll — you'll be notified on completion.

The agent itself uses `superpowers:using-git-worktrees` for isolation (see worktree section below) and `superpowers:subagent-driven-development` if it needs to fan out further.

**Dependency trap — the most common failure mode:** When issues are sequential or dependent (task B blocked by task A), the correct response is still to dispatch ONE background agent that handles them sequentially — NOT to do the work inline. A dependency between tasks changes the agent's prompt, not the workflow.

### Workflow B — Complex / design-heavy work

**Use for:** new feature, architectural change, multi-system refactor, ambiguous requirements, anything where a written spec + plan is more valuable than jumping straight to edits.

Invoke the `design-session` skill (or `/design-session <slug>`). It runs the full `grill-with-docs` → PRD → issues → triage → docs-PR flow inline in this session, temporarily switched to Opus for the duration — the human drives the conversation directly here rather than in a separate pane. Implementation is dispatched separately from the main session (Workflow A) after the design session completes.

### The main session is a dispatcher — never an implementer

PR-bound work (any change that touches source code, config, or docs and will become a commit) MUST be executed by a background agent — always. There are no exceptions:

| Rationalization                            | Correct response                                         |
| ------------------------------------------ | -------------------------------------------------------- |
| "Tasks are sequential, not parallelizable" | Dispatch one agent to handle them in order               |
| "It would be faster to do it inline"       | Dispatch a background agent. Speed is not the constraint |
| "The change is tiny"                       | Workflow A exists for tiny changes. Use it               |
| "I already started exploring the code"     | Stop. Spawn the agent with your findings in the prompt   |

## Git worktrees for isolated work

Worktree directory: always `<project-root>/.worktrees/<branch>` — the `.worktrees/` folder sits directly at the git repository's toplevel, never inside `.claude/`, never at a global path.

For any code change that will become a PR — feature, bugfix, refactor, config change — create a worktree first via `superpowers:using-git-worktrees` **before editing any file**. No quick edits in the root workspace. Root workspace must be clean at all time.

User-scope constraints (override the skill's defaults):

- **Always compute the absolute path** using `$(git rev-parse --show-toplevel)/.worktrees/<branch-name>`. Never use a CWD-relative path like `.worktrees/<branch>` — the CWD may be a subdirectory (e.g. `.claude/`) and will produce the wrong location.
- **Most common mistake — `.claude/worktrees/` is FORBIDDEN:** **Explicitly forbidden locations:** `.claude/worktrees/`, `worktrees/` (no leading dot), any path outside the project repo root, and any global path including `~/.config/superpowers/worktrees/`.
- Use `git -C <worktree-path> <cmd>` for all git operations — do not `cd` into the worktree, even though `using-git-worktrees` shows `cd`.
- **`EnterWorktree` accepts any path, including `.worktrees/<branch>`** — it is NOT restricted to `.claude/worktrees/`. Agents that read the `using-git-worktrees` skill sometimes incorrectly conclude that `EnterWorktree` is forbidden and fall back to raw `git worktree add` bash commands. Always prefer `EnterWorktree` over manual git commands.

## Specs and plans as PRs

Never commit spec or plan files (e.g. superpowers specs, grill's adrs, context , implementation plans) directly to the main branch in the root workspace. Any agent producing a spec or plan must create a worktree, commit there, and open a PR — same as code changes. The root workspace main branch must stay clean.

## Finishing a branch / opening PRs

Use `superpowers:finishing-a-development-branch` to verify tests, then push and open the PR (option 2). For PR title/body conventions specifically, `authoring-pr:create-pr` covers the formatting.

## Agent model selection

The workspace default model (set in `settings.json`) is `claude-sonnet-4-6`. This section governs agent dispatch, not the main session.

**Default to `sonnet` for most tasks.** Use `opus` when the task genuinely warrants deeper reasoning — or when the user explicitly requests it.

| Model    | When to use                                                                                                                                               |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `haiku`  | Trivial lookups only: reading/summarising a single file, single-step data extraction, targeted searches                                                   |
| `sonnet` | Standard dev work: bugfixes, features, tests, refactors, multi-step tasks with clear requirements                                                         |
| `opus`   | Complex tasks warranting deep reasoning: ambiguous requirements, cross-system architectural changes, nuanced design trade-offs — or explicit user request |

**Upgrade to `opus` when any of the following apply:**

- The user explicitly requests it: "think hard", "think harder", "ultrathink", "think smart", "work smart", "use opus", "with opus", "on opus", or any direct reference to opus as a model
- The task involves significant architectural ambiguity or multi-system reasoning that would benefit from deeper analysis
- The task requires investigation or debugging — tracing unexpected behavior, diagnosing root causes, or navigating unfamiliar code paths where shallow reasoning leads to wrong fixes
- Requirements are unclear enough that getting the design wrong would be costly to unwind

**When in doubt, stay on `sonnet`.** The goal is to match model capability to task complexity — not to default to the most expensive option.

# Team-agent dispatch

When work benefits from a shared task surface and multiple coordinated members, use the team pattern.

**Required two-step dispatch — do not skip step 1:**

1. **`TeamCreate`** — create the team first, with a descriptive `team_name` (e.g. `<topic>-team`) and a one-line `description`. A bare `Agent` call with only a `name` parameter is NOT a team and does not satisfy this rule.
2. **`Agent`** — spawn the worker as a member of that team. Required parameters:
   - `team_name`: matching the team you just created
   - `name`: the member's identity (used by `SendMessage` and task ownership)
   - `isolation: "worktree"`: the worker operates in an isolated worktree, never on the user's main checkout
   - `subagent_type`: pick based on capability needs (`general-purpose` for full tools)

**Track the delegation** with a single `TaskCreate` entry assigned to the worker (`owner: <member-name>`, `status: in_progress`). Update or close it when the worker reports back.

**When the work is complete**, either gracefully shut the team down via `SendMessage` with `{type: "shutdown_request"}`, or leave the team idle if more iterations are likely on the same topic.

**Reuse teams across tasks — do not tear down and rebuild for every new task.** A team is just a container; it can hold members with different specialties. When the user starts a new task while a team is still open:

- **First choice:** spawn a NEW member into the existing team (`Agent` with the same `team_name` plus a fresh `name` and a task-specific prompt). Different members can coexist — e.g. an `issue-filer` and a `pr-reviewer` in the same team.
- **Last choice:** delete the team and create a new one. Only do this when the leader-can-only-manage-one-team constraint actively blocks you AND the existing team is genuinely done (idle workers, all artifacts shipped, user has signaled closure).
- **Implication for naming:** prefer a durable team name (e.g. `<repo>-team`, `<workstream>-team`) over a single-task name (`<one-pr>-team`), so the team can host follow-up work without rename friction.

**Do not** execute PR-bound work directly in the master session even when "it would be faster" — the user has corrected this before. Speed is not the constraint; isolation and addressability are.

## memsearch auto-context

At the start of any task, extract the **core subject keywords** from the task description — the main noun-phrase or concept being worked on — and run memsearch if `.memsearch.toml` exists in the current project root.

Keyword extraction examples:

- "Review units against naming convention in ADR 0005" → `naming convention`
- "Write a naming convention ADR from oolio-one/sandbox stacks" → `naming convention`
- "Grill issues #204 & #205 against the domain model" → `domain model`
- "Fix DynamoDB table names to follow ADR 0005" → `DynamoDB naming convention`
- "CiliumNetworkPolicy egress for vouchers-service to NATS" → `CiliumNetworkPolicy egress`
- "How does the secret store work?" → `secret store`

Then run:

memsearch search "<extracted keywords>" -c <collection from .memsearch.toml> --top-k 5

Format the results as a fenced block and use as orientation before reading any CONTEXT.md or docs/ files. If memsearch errors or returns no results, silently continue — do not halt.

**Review and alignment workflows — never skip memsearch first:**

For any task that involves matching code, PRs, or changes against a domain rule — ADR alignment, code review, compliance checks, convention audits — run memsearch on the rule topic **before** listing files, reading diffs, or building any mapping from titles alone. Titles are often non-obvious: an ADR on ports/adapters, secret injection, or terminal-state enforcement will not surface from a file listing. Memsearch catches the intent that titles miss.

The temptation to list files first and infer coverage from names is a known failure mode. The correct chain for any review/alignment task:

1. `memsearch search "<rule or ADR topic>" -c <collection> --top-k 5` — retrieve indexed knowledge on the domain rule first.
2. Use memsearch results to identify which ADRs, conventions, or constraints apply before reading any code.
3. Then open files, diffs, or PRs with that context already loaded.

**Never-skip rule:** If the task involves matching code against a domain rule (ADR, naming convention, compliance spec, architectural constraint), memsearch on the rule topic is **mandatory** — not optional — even if you believe you already know the rule from session memory.

## Memory (remote temporal — Graphiti via `memory` MCP server)

Ambient progress-state, not a decision store: a self-service, non-authoritative catch-net so
a later cold start (yours or someone else's) can pick up smoothly. Compose service
(`graphiti-mcp`) lives in `plugins/harness5/infrastructure/docker-compose.yml`; entity-type schema at
`plugins/harness5/infrastructure/config.yaml`; env vars in `plugins/harness5/infrastructure/.env.example`.

When current work is scoped to a GitHub issue/PR/ticket — i.e. the same scope where
`agentic-memory-read`'s trigger conditions apply (cold start, resuming a ticket, descending
into a child ticket) — `agentic-memory-write` is the correct place to persist progress-state,
**not** the generic per-project file-based auto-memory system (the `memory/*.md` files
described under this file's "# auto memory" section). That file-based system is for durable
facts about the user/project/feedback that outlive a single ticket; `agentic-memory-write` is
for ambient, ticket-scoped catch-net state that a cold start needs and that would otherwise be
lost.

- **Cold-start / picking up work:** before touching code, use the `agentic-memory-read`
  skill for your resolved scope — `owner/repo#<issue>` derived from the git remote plus
  branch/PR/task-brief (`owner/repo` alone for ad-hoc work with no issue). Re-query when you
  descend into a child ticket mid-session (epic scope → ticket scope).
- **During work:** use the `agentic-memory-write` skill, event-driven — on a blocker, on
  discovered drift (delivered ≠ ticket intent), at a stopping point (session end,
  context-limit handoff, done-pending-verification), on a silent descope, or when resolving a
  previously-noted blocker/drift. Write standup-prose to the next developer — where it
  stands, what's the catch, where to pick up — not a rigid field template, and not
  continuous per-step logging.
- **Three homes:** ADR (architectural *why*) / GitHub Issues (*what*, system of record) /
  Memory (tacit catch-net, non-authoritative). Memory never substitutes for ticket/ADR
  hygiene — if a fact should update or close the ticket, update the ticket; a real
  architectural decision still goes to an ADR.
- Never write secrets to memory.
