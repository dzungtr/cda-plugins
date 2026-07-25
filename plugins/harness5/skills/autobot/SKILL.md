---
name: autobot
description: Autonomously build a complete feature, bugfix, or project end-to-end from a single topic/initiative/epic — scope-review gating, nested autonomous design sessions, implementation dispatch, and autonomous PR review & merge, all tracked through a GitHub issue tree. Invoke explicitly with /autobot <topic>.
disable-model-invocation: true
---

# autobot — autonomous initiative builder

Turn a topic/initiative/epic into merged PRs with no human in the loop, except two escape hatches: the size checkpoint (step 4) and `ready-for-human` flags.

## Role of the main session (non-negotiable)

The main session is a pure orchestrator:

- It stays at the repo root for the entire run. It never edits files, never reads PRDs, briefs, or diffs.
- **The GitHub issue tree is the only state.** The main session retains just the root epic issue number; everything else (what's designed, blocked, merged) is reconstructed on demand via `gh` queries. This makes autobot resumable: a fresh session re-enters from the epic number alone and continues.
- **Subagent report contract:** every subagent must end with a ≤10-line structured summary — verdict, URLs created, next-eligible work. Never ask a subagent for more detail than that.
- **The root epic body is the live dashboard.** After every state change (design done, PR merged, node flagged human), update the tree-shaped checklist in the epic body. The human watches the epic issue, not the terminal.

## Preconditions (check first; refuse to start if any is unmet)

- `gh auth status` succeeds and the repo has a GitHub remote. GitHub Issues is the only backlog backend — no markdown fallback.
- Root workspace is clean.
- Sub-issue nesting: use the GitHub sub-issue API to link children to parents; if unavailable, fall back to `- [ ] #n` task lists in parent issue bodies.

## Models

- Design sessions, architecture sessions, review/merge: `fable`; if the spawn is rejected, fall back to `opus`.
- Implementers, results promotion, scope-review: `sonnet`.
- All subagents: `run_in_background: true`, work-describing names (`design-<slug>`, `impl-<slug>-<issue#>`, `review-pr-<n>`), and `isolation: "worktree"` for anything that edits files.

## The loop

0. **Bootstrap.** Create the root epic issue from the user's topic (goal statement + empty dashboard section). This is the tree root; every node below hangs off it.

1. **Scope-review the node.** Spawn a subagent to run `/scope-review` on the node's goal. It returns only PASS/FAIL plus the three-line criteria rationale.

2. **PASS → autonomous design session.** Spawn a design subagent (fable/opus) with the autonomous preamble from [references/prompts.md](references/prompts.md): run `/design-session <goal>`, answer every interview question with its own recommended answer, self-approve the PRD and issue breakdown, skip the model-switch steps (it is already on the target model). The subagent itself publishes the PRD issue **as a child of the current parent node**, the slice issues under the PRD, runs triage briefs, and raises the docs PR — then reports back only the URLs.

3. **FAIL → architecture session.** Spawn a decompose-only subagent (fable/opus) using the prompt scope-review's FAIL output suggests: map the goal into an ordered sequence of independent PR slices — decompose only, design nothing. It publishes one child issue per slice under the current parent in dependency order. Each child then re-enters the loop at step 1. **Max decomposition depth: 3.** A node still failing scope-review at depth 3 is labeled `ready-for-human` and its branch stops.

4. **Size checkpoint (the only planned pause).** When decomposition settles, count leaf slices. If the tree has **more than 20 leaves**, pause: post the full tree and effort estimate on the epic, notify the human, and wait for go-ahead. At 20 or fewer, proceed without pausing.

5. **Implementation dispatch.** One `sonnet` implementer per **unblocked** slice issue, up to 3 concurrent, each in its own worktree. The prompt is the issue URL + its agent brief. The implementer implements, tests, opens a PR whose body contains `Closes #<slice-issue>`, and returns the PR URL. Dependents become eligible only when their blocker's PR merges.

6. **Review & merge.** Fresh fable/opus reviewer per PR — never the implementer reviewing its own work. Hard merge gates, all three required: **CI green + acceptance criteria met + no unresolved review findings.** The reviewer inspects the actual diff for over-editing beyond the brief's scope — never trusts the implementer's self-report. Findings go back to an implementer agent on the same branch; **max 2 fix rounds** (a post-merge "rebase on main" instruction is round zero and doesn't count). Still failing after round 2 → label the issue `ready-for-human`, comment the outstanding findings, leave the PR open, move on. Merge follows the repo convention (default squash); delete the branch and clean up the worktree. **Reindex after merge:** if the repo has a `.memsearch.toml` at its root and the merged PR touched any path it lists under `paths`, dispatch a `sonnet` subagent to run `/memsearch-index` so the semantic index reflects the merged docs — then continue without waiting. If the memsearch backend is unreachable (e.g. Milvus down), do not block the loop: label the epic node `ready-for-human` with a note that a reindex is owed, and move on. This applies equally to the docs PRs merged in step 7.

7. **Results promotion.** When all children of a PRD issue are merged, spawn a `sonnet` subagent to promote the PRD's filled Results section into the ADR "Measured results" stub via a docs PR (same review gate as step 6, including the post-merge reindex), then close the PRD issue.

8. **Done.** The run is complete when every node is terminal — closed-by-merge or `ready-for-human`. Post a final report on the epic: merged PRs, flagged items with reasons, results promoted. Close the epic **only if there are zero `ready-for-human` leftovers**; otherwise leave it open with the dashboard showing the remaining human work.

## Concurrency

- **Max 1 design/architecture session at a time.** Their docs PRs touch shared files (CONTEXT.md, ADRs); serializing them prevents conflicts and doubles as the budget throttle on the expensive models.
- **≤3 concurrent implementers** (worktree-isolated; the cap limits merge conflicts, not workspace conflicts).
- **Merges are serialized.** If the next PR conflicts with fresh `main`, its implementer gets a rebase instruction as fix-round zero.

## Failure & stalls

- **One-retry rule:** a subagent that dies or errors (API failure, crash, flaky CI) is respawned once with the same prompt. Second failure → label the node `ready-for-human` with a comment describing where it died, and move on.
- **Heartbeat:** schedule a wakeup every 20–30 minutes. On each wake, reconcile: any dispatched work with no completion notification **and** no issue-state change for 2 consecutive heartbeats gets its agent stopped and the one-retry rule applied.
- **`ready-for-human` never blocks the run.** Route around flagged nodes, keep every automatable branch moving, and surface the human-needed list in the epic dashboard as it grows. Slices that triage marks `ready-for-human` by nature (manual testing, judgment calls) get the same treatment: skip, flag, continue.

## Prompt templates

The five subagent prompt templates (scope-review, architecture, autonomous design-session preamble, implementer, reviewer/merger) live in [references/prompts.md](references/prompts.md).
