---
name: scope-review
description: Run before any design session or brainstorm to check whether the goal is PR-sized. Evaluates three criteria — deliverability, reviewability, independence — and returns PASS (proceed to /design-session) or FAIL (run an architecture session first). Does not decompose, design, or modify the goal.
---

# scope-review — Pre-Brainstorm PR-Boundary Gate

## When to invoke

**Always invoke before `/design-session` or `superpowers:brainstorming`.** Especially when:
- The goal describes a project phase, a multi-capability feature, or infra work that spans several concerns
- You are uncertain whether the work fits in one PR
- A previous brainstorm on a similar goal produced a PR that was too large to review

**Skip when:**
- Goal is clearly a single-file change or a well-scoped bugfix (use Workflow A directly)
- You already have a slice list from an architecture session and you are working on a named slice

## The Three Criteria

Evaluate the goal against all three. Any single FAIL means the overall verdict is FAIL.

### 1. Deliverability
Can this be shipped as a single PR where `main` is runnable and more valuable after the merge — with no dependency on other unmerged work to be useful?

- **PASS:** main is independently deployable after this PR
- **FAIL:** requires other PRs to land first, or leaves main in a broken or incomplete state

### 2. Reviewability
Is the scope small enough for a focused review session — one coherent concern a reviewer can evaluate without context-switching?

- **PASS:** touches one service, one config area, or one capability
- **FAIL:** reviewer would need to context-switch between multiple concerns to evaluate the diff

### 3. Independence
Does this slice stand alone as a unit of observable value — not just scaffolding for the next thing?

- **PASS:** the change adds a working feature, a measurable improvement, or a clean verifiable state on its own
- **FAIL:** it is purely groundwork with no standalone observable value

## Model selection

Run this evaluation with the `opus` model. Scope decisions are high-stakes judgment calls — getting the boundary wrong means a PR that is too large to review or a design session that produces a plan that can't be shipped independently.

## Process

1. Read the goal as stated. Do not reframe or decompose it.
2. Evaluate each criterion. For each, state your reasoning in one sentence.
3. Output the verdict using the exact format below.
4. Stop. Do not invoke any other skill. The user drives the next step.

## Output format

### PASS

```
PASS — scope is PR-sized.

Deliverability: ✓ <one sentence rationale>
Reviewability:  ✓ <one sentence rationale>
Independence:   ✓ <one sentence rationale>

Proceed to /design-session with goal: "<goal as stated>"
```

### FAIL

```
FAIL — scope is too large for a single PR.

Deliverability: [✓ or ✗] <one sentence rationale>
Reviewability:  [✓ or ✗] <one sentence rationale>
Independence:   [✓ or ✗] <one sentence rationale>

Before designing, run an architecture session to produce an ordered
slice list. Then re-run /scope-review on the first slice.

Suggested architecture session prompt:
  "Map out <goal> as an ordered sequence of independent PR slices.
   Each slice must leave main runnable and add standalone value.
   Output: a numbered list of slices with a one-line goal for each.
   Do not design any slice — only decompose."
```

## Examples

**PASS example:**
```
/scope-review "add liveness probe to kape-ingestion deployment"

PASS — scope is PR-sized.

Deliverability: ✓ adding a probe is a self-contained manifest change; main is valid without it and more robust with it
Reviewability:  ✓ single manifest file, single concern
Independence:   ✓ the probe adds observable operational value on its own (pod restarts on hang)

Proceed to /design-session with goal: "add liveness probe to kape-ingestion deployment"
```

**FAIL example:**
```
/scope-review "set up observability for kape phase 2"

FAIL — scope is too large for a single PR.

Deliverability: ✗ "observability" implies metrics, logs, and alerting — merging partial observability leaves main with inconsistent coverage
Reviewability:  ✗ a reviewer would need to context-switch across ServiceMonitor, Prometheus rules, Grafana dashboards, and alert routing
Independence:   ✗ individual pieces (e.g. just the ServiceMonitor) add value, but "phase 2 observability" as a whole is a bundle

Before designing, run an architecture session to produce an ordered
slice list. Then re-run /scope-review on the first slice.

Suggested architecture session prompt:
  "Map out 'set up observability for kape phase 2' as an ordered sequence
   of independent PR slices. Each slice must leave main runnable and add
   standalone value. Output: a numbered list of slices with a one-line
   goal for each. Do not design any slice — only decompose."
```

## What this skill does NOT do

- Does not produce a slice list or architecture breakdown
- Does not modify or reframe the goal
- Does not invoke brainstorming or any other skill
- Does not ask clarifying questions about the goal
