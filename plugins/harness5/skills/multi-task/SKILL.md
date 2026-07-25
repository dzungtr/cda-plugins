---
name: multi-task
description: Use when a task has more than 3 steps, has a concrete deliverable (PR, GitHub issue, investigation report, config change), or a Q&A thread is heading toward 3+ back-and-forth exchanges. Invoke before starting the work, not after.
---

# multi-task — Delegate to Team Agent, Free the Main Session

## Overview

Long or goal-oriented work must be delegated to a background team agent — never executed inline in the main session. The main session is for directing work and receiving results, not doing it. Keeping it free lets the user start the next task immediately.

**Violating the letter of this rule is violating the spirit.**

## Trigger Checklist

Invoke this skill if ANY of the following is true:

- [ ] Task has **more than 3 steps** (e.g. investigate → fix → test → PR)
- [ ] Task has a **concrete deliverable**: PR, GitHub issue, investigation report, runbook, config change, ADR
- [ ] Q&A thread is approaching **3 back-and-forth exchanges** — delegate to a research agent instead of continuing inline
- [ ] Task requires **file edits** of any kind (always pairs with `worktree-pr`)

When in doubt: delegate. The cost of an unnecessary team agent is low. The cost of a blocked main session is high.

## Dispatch Sequence

Follow this order exactly. Do not skip steps.

```
digraph dispatch {
    "Task identified" [shape=doublecircle];
    "Team exists?" [shape=diamond];
    "TeamCreate" [shape=box];
    "Agent (run_in_background=true)" [shape=box];
    "Report team+member name" [shape=box];
    "Return control to user" [shape=doublecircle];

    "Task identified" -> "Team exists?";
    "Team exists?" -> "Agent (run_in_background=true)" [label="yes"];
    "Team exists?" -> "TeamCreate" [label="no"];
    "TeamCreate" -> "Agent (run_in_background=true)";
    "Agent (run_in_background=true)" -> "Report team+member name";
    "Report team+member name" -> "Return control to user";
}
```

### Step 1 — TeamCreate (if no team yet)

```
TeamCreate(
  team_name: "<verb>-<scope>"        # e.g. "fix-cilium-egress", "investigate-cnpg-stuck"
  description: "<one sentence goal>"
  agent_type: "general-purpose"      # use specific type only if needed
)
```

### Step 2 — Agent (always background)

```
Agent(
  team_name: "<same as above>"
  name: "<role handle>"              # e.g. "engineer", "investigator", "pr-author"
  subagent_type: "general-purpose"   # general-purpose for file edits; Explore for read-only research
  run_in_background: true            # ALWAYS true — never block main session
  prompt: """
    <self-contained brief>
    Context: <what the user is trying to accomplish and why>
    Task: <what specifically to do>
    Constraints: <worktree path, branch, repo, AWS profile, region if relevant>
    Deliverable: <PR URL / issue URL / report / etc.>
  """
)
```

### Step 3 — Return control

Report back in one line:
> "Delegated to team `<name>` / member `<handle>`. You'll be notified when it completes."

Then **stop**. Do not poll. Do not ask follow-up questions. Do not start the work yourself.

## Writing the Agent Prompt

The agent starts with zero context from this conversation. The prompt must be fully self-contained.

| Include | Omit |
|---------|------|
| Goal and why it matters | Conversation history summaries |
| Exact repo path / worktree path | Vague references ("the thing we discussed") |
| Branch name convention | Assumed knowledge |
| AWS profile + region if AWS work | |
| PR/issue target repo | |
| Definition of done (what counts as complete) | |

For code changes, append: _"Follow the worktree-pr skill: create worktree at `.worktree/<branch>`, use `git -C` for all git ops, open draft PR when done."_

## Choosing subagent_type

| Work type | subagent_type |
|-----------|---------------|
| File edits, PRs, infra changes | `general-purpose` |
| Read-only research, codebase exploration | `Explore` |
| Code review against a plan | `superpowers:code-reviewer` |
| PR authoring with conventions | keep `general-purpose`, reference `authoring-pr:create-pr` in prompt |

## Red Flags — STOP

These thoughts mean you're about to block the main session:

- "It's only a few steps, I'll just do it inline" → **STOP. Count the steps. >3 = delegate.**
- "Let me gather some context first, then I'll delegate" → **STOP. Gather context IN the agent prompt.**
- "I'll do the first part here and delegate the rest" → **STOP. Delegate the whole thing.**
- "The user seems to want a quick answer" → **STOP. A background agent answers just as fast and frees the session.**
- "I need to ask a clarifying question before delegating" → Only ask if the answer would change the team/agent topology. Otherwise include your best assumption in the prompt and note it.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Spawning Agent without TeamCreate | Always TeamCreate first — it creates the coordination surface |
| `run_in_background: false` | Always `true`. Never block. |
| Bare Agent call (no `team_name`) | Not the team pattern. Always include `team_name`. |
| Vague agent prompt ("fix the thing") | Self-contained brief with context, constraints, deliverable |
| Polling after dispatch | Don't. You'll be notified automatically. |
| Doing first 2 steps inline "to save time" | Those 2 steps become 10. Delegate everything. |
