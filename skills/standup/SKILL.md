---
name: standup
description: Project-aware daily triage. Aggregates external signals (Jira, Sentry, observability) declared in .claude/standup.json and reconciles them against open GitHub Issues. Produces a 5-bucket ranked report (ACT NOW, TRACKED-UPDATED, IN FLIGHT, STALE, Plan) and persists it to .claude/standups/YYYY-MM-DD.md. Use when the user runs /standup, asks for their daily plan, or wants to know what to work on next in the current repo. Requires the highest available Claude model (currently Opus 4.7) — reconciliation needs nuanced reasoning.
---

# /standup — Daily triage ritual

You are running the `/standup` skill in the user's current project. Follow the steps below in order. Halt with a clear error if any precondition fails.

## 1. Load config

Determine the project root: it is the directory containing the `.git/` directory at or above the current working directory. If there is no enclosing git repo, halt with:

> **standup: not in a git repository.** `/standup` is project-aware and must be run from inside a project repo. Aborting.

Read `<project-root>/.claude/standup.json`.

### Halt conditions

- **File missing.** Halt with this exact message (substitute `<project-root>`):

  > **standup: `<project-root>/.claude/standup.json` not found.**
  >
  > Create it with at least one datasource. Schema:
  >
  > ```json
  > {
  >   "datasources": [
  >     {
  >       "name": "<source-label>",
  >       "description": "<human description>",
  >       "tool": "<MCP tool ID>",
  >       "params": { ... }
  >     },
  >     {
  >       "name": "<source-label>",
  >       "description": "<human description>",
  >       "command": "<shell command producing JSON>"
  >     }
  >   ]
  > }
  > ```
  >
  > A fully worked example is at `~/.claude/skills/standup/references/example-config.json`.

- **Malformed JSON.** Halt with: `standup: failed to parse <project-root>/.claude/standup.json: <parser error>`. Do not attempt to recover.

- **Schema violations.** The config object MUST have a `datasources` array with at least one entry. Each entry MUST have:
  - `name` (string, non-empty)
  - `description` (string, non-empty)
  - exactly one of: (`tool` AND `params`) OR `command`

  On any violation, halt with: `standup: invalid config — datasource[<index>]: <reason>`. Examples:
  - `datasource[0]: missing 'name'`
  - `datasource[2]: must define exactly one of 'tool' (with 'params') or 'command'`
  - `datasource[3]: 'name' must be a non-empty string`

After validation, store the parsed config in working memory as `config.datasources` for the next step.

## 2. Run datasources in parallel

For every entry in `config.datasources`, dispatch its work in a SINGLE batch of tool calls (one assistant turn, multiple parallel tool invocations). Do not run them sequentially — parallelism is required so the user-facing latency is bounded by the slowest datasource, not the sum.

For each entry:

- If the entry has a `tool` field: call that MCP tool with `params` exactly as given. Do not modify or augment `params`.
- If the entry has a `command` field: invoke the Bash tool with `command` exactly as given. Do not add quoting, redirects, or pipes.

Capture the full raw output for each datasource. Build an in-memory map:

```
rawOutputs: {
  "<datasource.name>": { ok: true|false, output: <string-or-tool-result>, error?: <string> }
}
```

### Failure handling

If a datasource fails (non-zero exit, MCP error, timeout): record `{ ok: false, error: <message> }` and CONTINUE. Do not halt the whole standup. The report (Step 6) will note the failure inline so the user knows that datasource was skipped.

## 3. Pull GitHub state

In the SAME parallel batch as the datasource calls (Step 2) — or as a second parallel batch issued immediately after — run BOTH of the following via the Bash tool:

- `gh issue list --state open --json number,title,labels,assignees,body --limit 200`
- `gh pr list --state open --json number,title,headRefName --limit 200`

The `--limit 200` cap is intentional: a healthy repo should fit comfortably under this. If either command returns 200 rows, surface a one-line warning in the report ("note: hit 200-issue cap, results may be truncated").

Parse each as JSON and store:

```
githubState = {
  issues: <array of {number, title, labels, assignees, body}>,
  prs:    <array of {number, title, headRefName}>
}
```

### Failure handling

If `gh` is not installed or the user is not authenticated, halt with:

> **standup: `gh` CLI unavailable or not authenticated.** Run `gh auth status` to diagnose. Aborting.

GitHub state is required — without it reconciliation cannot run.

## 4. Reconcile by source-name label

For each datasource `D` in `config.datasources`:

1. Filter `githubState.issues` to those carrying a label equal to `D.name`. Call this set `trackedIssues[D.name]`.
2. Read the full output captured for `D` in `rawOutputs[D.name]`. Identify the discrete external items (Jira tickets, Sentry issues, CloudWatch alarms, etc.) — interpret the structure natively; do NOT use a regex or fixed JSONPath, since each datasource shape differs.
3. For each external item `X`:
   - **Match step.** Read the title and body of every issue in `trackedIssues[D.name]`. Decide using full-context judgement whether any of them describes the same real-world problem as `X`. If yes → `X` pairs with that issue. Use semantic matching: equivalent stack traces, equivalent failure modes, equivalent ticket IDs, paraphrased summaries all count.
   - **No match.** `X` is *untracked* → bucket = `ACT NOW`.
   - **Match found.** `X` is *tracked* → check the issue's last meaningful activity (newest comment, body edit, or label change). If the external item is fresh (the source signal indicates activity in the last 7 days, e.g. Sentry `lastSeen`, Jira `updated`, alarm `StateUpdatedTimestamp`) → bucket = `TRACKED-UPDATED`. Otherwise → bucket = `STALE`.
4. Also flag `trackedIssues[D.name]` entries that pair with NO external item *and* whose own most recent activity is >7 days old → bucket = `STALE` (close candidate).

### Worked example

Datasource `prod-errors` returns 3 Sentry issues:
- `S1`: TypeError in `checkout.handlePayment`, 412 events / 24h, level=fatal, lastSeen=now.
- `S2`: DatabaseTimeoutError, 230 events / 24h, lastSeen=now (was 50 events 24h ago).
- `S3`: ChunkLoadError, 0 events / 24h, lastSeen=12d ago.

Open GitHub Issues with label `prod-errors`:
- `#127`: title "DatabaseTimeoutError spike on /api/orders" — body describes the timeout pattern.
- `#119`: title "Cosmetic: ChunkLoadError on stale tabs" — body discusses the chunk-load error class.

Reconciliation:
- `S1` → no matching issue → `ACT NOW` (untracked, fatal, high frequency).
- `S2` ↔ `#127` (same DB timeout pattern) → `TRACKED-UPDATED` (Sentry count jumped 50→230).
- `S3` ↔ `#119` (same ChunkLoadError class) → `STALE` (no fresh signal in 24h *and* the source itself shows lastSeen=12d).

Store the bucketed results as `reconciled = { actNow: [...], trackedUpdated: [...], stale: [...] }` for use in Steps 5 and 6.

## 5. Detect in-flight work

After reconciliation (Step 4), walk every paired issue across `reconciled.trackedUpdated` and `reconciled.stale`. An issue is **in flight** if ANY of these signals is true:

1. **Open PR linked.** A PR in `githubState.prs` references this issue by:
   - branch name containing `<number>` (e.g. `fix/127-timeout`), OR
   - PR title or `headRefName` containing the issue number, OR
   - the issue body or comments link to the PR (the agent should infer this from `gh issue view <n>` if needed — but for v1, branch-name match is sufficient and avoids extra API calls).
2. **`in-progress` label.** The issue's `labels` array contains a label with name `in-progress`.
3. **Assigned.** The issue's `assignees` array is non-empty.

When an item meets any of these signals: move it from its current bucket (`TRACKED-UPDATED` or `STALE`) into `reconciled.inFlight`. It will appear in the report as **context only** and MUST NOT appear in the Plan section's suggested-dispatch list.

Untracked items (`reconciled.actNow`) cannot be in flight by definition.

After this step, the bucket map is finalised:

```
reconciled = { actNow: [...], trackedUpdated: [...], inFlight: [...], stale: [...] }
```

## 6. Render the 5-bucket report

Render a Markdown report following the template below EXACTLY. Match the headers, emojis, prefix labels (`[<datasource-name>]`), and ordering. Numbered items in `ACT NOW` and `TRACKED-UPDATED` are continuous (do not restart numbering between sections).

Ranking inside each bucket: severity × age × frequency (basic v1 — see "Future improvements" in the spec). For Sentry-like signals: `level=fatal` > `level=error` > `level=warning`; higher event count first; older `firstSeen` is a tiebreaker (long-standing pain rises). For Jira: priority Highest > High > Medium > Low. For alarms: alarms in `ALARM` longest first. The agent uses judgement when sources don't expose obvious severity fields.

### Plan section

After the four buckets, render a `## Plan for today` section with:
- **Suggested top 3 to dispatch in parallel** — three items pulled in priority order from `ACT NOW` and `TRACKED-UPDATED` (never `IN FLIGHT`, never `STALE`). Each line names the issue (`#N`) or proposes "New issue from item #X" if untracked.
- **Needs your judgement before dispatch** — items that are high-priority but ambiguous (e.g. need device-specific repro, may already be resolved). 1–4 entries.

### Template (worked example from spec section 7 — use this verbatim as the structure)

```markdown
# Standup — 2026-05-08 (window: last 24h)
**Repo:** tillpos-tony/myapp  •  **Datasources:** qa-bugs, pm-features, prod-errors, prod-alarms

## 🔴 Act now — untracked, high signal
1. **[prod-errors] TypeError in checkout.handlePayment** — 412 events in 24h, level=fatal
   No matching GitHub Issue. Suggested: open issue with label `prod-errors`, dispatch agent.
2. **[qa-bugs] BUG-481: Login fails on iOS Safari** — priority Highest
   No matching GitHub Issue. Suggested: open issue with label `qa-bugs`.

## 🟡 Tracked — updates worth checking
3. **#127** [prod-errors] DatabaseTimeoutError — Sentry count jumped 50→230 in 24h.
4. **#142** [qa-bugs] BUG-462: Cart total miscalculation — Jira moved to "In Progress" yesterday. No PR yet.

## 🟢 In flight
- **#118** Refactor checkout flow (PR #214 open, draft)
- **#135** [pm-features] PROJ-301: Bulk export — assigned, in-progress

## ⚪ Stale
- **#102** [qa-bugs] BUG-401: Tooltip alignment — last Jira update 12d ago
- **#119** [prod-errors] ChunkLoadError — Sentry count 0 in 24h, may be resolved

## Plan for today
**Suggested top 3 to dispatch in parallel:**
- #127 (DatabaseTimeoutError — escalating)
- New issue from item #1 (TypeError — fatal, blocking users)
- #142 (Cart miscalculation — QA verified, ready for fix)

**Needs your judgement before dispatch:**
- Item #2 (Safari bug — may need device-specific repro first)
- #119 — verify resolved before closing
```

### Header line

- Title: `# Standup — YYYY-MM-DD (window: last 24h)` (today's date, ISO).
- Subhead: `**Repo:** <owner>/<name>  •  **Datasources:** <comma-separated names>`. Resolve `<owner>/<name>` from `gh repo view --json nameWithOwner -q .nameWithOwner`.

### Failed datasources

Any datasource that failed in Step 2 appears as a one-liner under the subhead, e.g.:

> _Note: datasource `prod-alarms` failed (`AccessDenied`); skipped._

Print the rendered report to the terminal AS the final user-facing output of the skill.

## 7. Persist artifact + ensure gitignore

### 7a. Ensure gitignore entry

Read `<project-root>/.gitignore` if it exists. Look for an entry that ignores `.claude/standups/` — accept any of:
- exact line `.claude/standups/`
- exact line `.claude/standups`
- exact line `/.claude/standups/`
- exact line `/.claude/standups`

If no matching entry is found:
1. Append the line `.claude/standups/` (with a leading newline if the file does not end in one) to `<project-root>/.gitignore`. Create the file if it doesn't exist.
2. After Step 7b, append a one-line note to the bottom of the rendered report: `_Note: appended `.claude/standups/` to .gitignore._`

If a matching entry already exists, do NOT modify the file. Do not surface a message — silence is the success signal.

### 7b. Write the artifact

Compute today's date in ISO (YYYY-MM-DD) using the system clock — e.g. via `date -u +%Y-%m-%d`. Ensure `<project-root>/.claude/standups/` exists (create it if not). Write the full rendered Markdown report to `<project-root>/.claude/standups/<YYYY-MM-DD>.md`, overwriting any existing file for the same day.

After writing, append the file path to the very end of the terminal output:

> _Saved to `.claude/standups/<YYYY-MM-DD>.md`._
