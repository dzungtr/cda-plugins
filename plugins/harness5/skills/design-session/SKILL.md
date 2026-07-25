---
name: design-session
description: Use when the human asks to design, plan, or build a non-trivial feature, refactor, or change that needs upfront design (multiple files, architectural decisions, ambiguous requirements, "let's build/design/plan X"). Runs the full grill-with-docs → PRD → issues flow inline in this session on Opus. SKIP for: small bugfixes, single-file edits, well-scoped changes with clear requirements, or pure questions.
---

# design-session

Run the full `grill-with-docs` → PRD → issues → triage → docs-PR flow inline in this main session, temporarily elevated to Opus for the duration.

## When to invoke

**Trigger when:**
- Human says "let's design X", "plan Y", "build a new feature for Z", "I want to add ..."
- Task involves architectural decisions, spans multiple files/systems, or has ambiguous requirements
- Requirements need clarification before code can responsibly be written
- A spec or implementation plan would be more valuable than jumping straight to edits

**Skip when:**
- Small bugfix, typo, config tweak, or single-file change
- Requirements are already explicit and unambiguous
- Human is asking a question, not requesting work
- Human explicitly says "just do it" / "quick change" / "no need to plan"

## Procedure

### 1. Confirm + collect context

Pick a short kebab-case slug for the feature (e.g. `payment-retry`, `multi-tenant-auth`). Capture:

- `pwd`, current git branch, repo root.
- Any file paths, constraints, or seed goals the human mentioned so far.

### 2. Switch to Opus (session-only)

Tell the human:

> "Switching to Opus for the design session. Please type `/model opus` and press **`s`** to select *this session only*, then confirm when done."

Wait for the human to confirm the switch before proceeding.

### 3. Run grill-with-docs

Invoke the `grill-with-docs` skill directly in this session. Interview the human relentlessly about every aspect of the design, challenge decisions against the domain model, and crystallise terminology in CONTEXT.md/ADRs.

Do not stop grilling until the human signals they are satisfied.

### 4. Write the PRD (and make it the coordination home)

Invoke `/to-prd` to synthesize the grilling into a PRD and publish it to the project issue tracker. The PRD is the durable spec — the "what & why" (problem, solution, user stories) plus the Implementation Decisions and Testing Decisions sections, which carry what used to be a separate implementation plan. Present it to the human for approval and iterate until approved.

The published PRD issue is **also the parent**: child issues (step 5) link directly to it as their parent, so it doubles as the **live coordination home and working ledger** for the initiative — the single object that answers "where is this initiative as a whole, and where do executing agents record what they produce." Once the PRD is approved, append these sections to its issue body:

- **Child checklist** — a placeholder section (populated in step 5 once children are published) using the tracker's native sub-issue/task-list syntax. Flag the HITL (`ready-for-human`) slices.
- **Handoffs** — a table with one row per *cross-slice* value that one slice produces and a sibling slice consumes (e.g. an export timestamp a downstream consumer must start from, baseline counts a validation slice checks against, root-caused rejects a loader must handle). Leave the values **blank**; the executing agents fill each in as its slice completes. This is what stops per-run state from stranding in ad-hoc files or dying in a closed child issue.
- **Results** — the durable, *cross-initiative* learnings the initiative exists to produce (sizing numbers, measured throughput/duration, anything that informs the *next* similar effort). Left blank now; filled as the work lands.
- **Definition of done** — must explicitly include: "promote the Results section into the repo (ADR/docs) via a docs-PR before closing this issue" (see Results promotion below).

Record the PRD issue's URL/ID — you will pass it to `/to-issues` in the next step as the parent.

The Handoffs/Results sections distinguish what the PRD issue *can* hold (live, within-initiative coordination) from what must outlive it (durable learnings) — the latter only become safe once promoted into the repo at close.

### 5. Break into issues and establish hierarchy

Invoke `/to-issues` to break the approved PRD into vertical-slice issues on the project issue tracker. Quiz the human on granularity, dependencies, and HITL vs AFK classification until they approve the breakdown, then publish the issues in dependency order **with the PRD issue set as their parent** using the tracker's native mechanism:

- **GitHub**: create each issue with `gh issue create`, then immediately link it as a sub-issue of the PRD issue via `gh api` (sub-issue API) or add it to the PRD issue's tasklist using `- [ ] #<number>` syntax in its body.
- **Linear**: pass `parentId: <prd-issue-id>` when creating each issue via the API.
- **Jira**: set the `parent` field to the PRD/epic issue key when creating each story.

After all child issues are published, update the PRD issue's child checklist section with links to every slice issue in dependency order, flagging HITL (`ready-for-human`) slices. Verify the tracker shows the children nested under the PRD issue before proceeding.

### 6. Triage issues

Invoke `/triage` for each published child issue. For each one: recommend a category (`bug` / `enhancement`) and state (`ready-for-agent` / `ready-for-human` / `needs-info`), post an agent brief if moving to `ready-for-agent`. Each brief **must name the PRD issue and point writers at its Handoffs/Results sections**, so executing agents know where to record what they find. Work through all issues before moving on.

### 7. Docs PR

Raise a PR for any ADR and docs changes (CONTEXT.md, ADRs, or other documentation) crystallised during the grilling session. In the same PR, **stub a "Measured results" section (or per-instance table) in the ADR** — left empty with a note that it is filled at initiative close — as the durable destination for the PRD issue's Results. Create a worktree, commit the changed docs files, open the PR, and report the PR URL.

### 8. Restore Sonnet

Tell the human:

> "Design session complete. Please type `/model sonnet` and press **`s`** to restore Sonnet for this session."

## Results promotion (at initiative close)

This step runs **after** execution completes — not during the design session — but the design session sets it up (steps 4 and 7) so it cannot be forgotten. Whoever closes the initiative:

1. Reads the now-filled **Results** section of the PRD issue.
2. Promotes those durable learnings into the ADR's "Measured results" stub via a docs-PR (same worktree + PR convention as step 7).
3. Only then closes the PRD issue.

Rationale: the PRD issue closes and drops out of every agent's working context, and is neither version-controlled nor co-located with the tooling the next initiative reuses. Learnings whose job is to feed the *next* effort must live in the repo before the initiative's working context evaporates.

## Notes

- Do NOT execute any implementation — that is dispatched separately from the main session as a Workflow A background agent after this design session completes.
- Model switching (`/model`) is a user-facing CLI command; Claude cannot switch it autonomously. Always prompt the human to do it at steps 2 and 8.
