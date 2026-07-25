# autobot subagent prompt templates

Substitute `<goal>`, `<parent-issue>`, `<slice-issue>`, `<pr>` before spawning. Every prompt ends with the report contract; do not omit it.

## Report contract (append to every prompt)

```
End your run with a structured summary of AT MOST 10 lines:
- VERDICT or OUTCOME (one line)
- URLS: every issue/PR you created, one per line
- NEXT: work that is now eligible, if any
Return nothing else. The orchestrator never reads your working detail.
```

## 1. scope-review — model: sonnet

```
Run /scope-review on this goal exactly as stated. Do not reframe or decompose it.

Goal: "<goal>"

Report PASS or FAIL plus the three one-line criteria rationales, nothing more.
```

## 2. architecture session (decompose only) — model: fable → opus

```
Map out "<goal>" as an ordered sequence of independent PR slices.
Each slice must leave main runnable and add standalone value.
Do not design any slice — only decompose.

Then publish one GitHub issue per slice in dependency order, each linked as a
sub-issue of <parent-issue> (fall back to a `- [ ] #n` task list in the parent
body if the sub-issue API is unavailable). Each issue body: one-line goal,
what "done" observably means, and a "Blocked by" field.
```

## 3. autonomous design session — model: fable → opus

```
Run /design-session <goal> in fully autonomous mode:

- You are already on the target model; skip both /model switch steps.
- For every interview question the grilling raises, adopt your own
  recommended answer and continue — never wait for a human.
- Self-approve the PRD and the issue breakdown when you are satisfied
  they are coherent; iterate yourself if they are not.
- Publish the PRD issue as a child of <parent-issue>, publish the slice
  issues under the PRD with triage labels and agent briefs, and raise the
  docs PR yourself (worktree + PR convention, never commit to main).
```

## 4. implementer — model: sonnet, isolation: worktree

```
Implement GitHub issue <slice-issue>. Read the issue body and its agent brief
comment first; the PRD issue it references is your spec — stay inside the
brief's scope, no opportunistic refactoring.

Work test-first, verify everything passes, then open a PR that references
the issue with "Closes #<slice-issue>" in the body.
```

## 5. reviewer / merger — model: fable → opus

```
Review PR <pr> for autonomous merge. You did not write this code.

Gates — ALL required before merging:
1. CI is green.
2. Every acceptance criterion on the linked slice issue is met.
3. No unresolved review findings.

Inspect the actual diff, not the implementer's summary — flag any change
beyond the brief's scope as a finding. If findings exist, post them as a PR
review and report OUTCOME: FIX-ROUND-NEEDED with the findings list; do not
merge. If all gates pass, merge using the repo's convention (default squash),
confirm the linked issue closed, and delete the branch.
```
