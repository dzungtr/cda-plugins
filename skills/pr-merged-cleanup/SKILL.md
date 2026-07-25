---
name: pr-merged-cleanup
description: Use when the user reports that a PR has been merged and there is a background team agent that raised that PR. Handles worktree removal, agent shutdown, and task completion.
---

# pr-merged-cleanup — Post-Merge Cleanup

## Overview

When a PR raised by a background agent is merged, three cleanup actions are required in order: mark any associated task done, remove the agent's worktree, then shut the agent down.

## Steps

Run these in order after the user confirms a PR is merged.

### 1. Mark the task complete (if one exists)

Use `TaskList` to find any task owned by the agent. If found, call `TaskUpdate` with `status: completed`.

### 2. Remove the worktree

Worktrees live at `.worktrees/<branch-name>` inside the repo. Derive the branch name from the PR (the agent reports it on completion, or check the PR). Then:

```bash
git -C <repo-root> worktree remove --force .worktrees/<branch-name>
```

If the branch still exists locally, delete it:

```bash
git -C <repo-root> branch -d <branch-name>
```

Use `--force` on the worktree remove only if the branch is already merged. Never force-delete unmerged local branches.

### 3. Shut down the agent

Send a shutdown request to the agent by name:

```json
{ "type": "shutdown_request" }
```

Wait for the `shutdown_approved` response before reporting done to the user.

## Quick Reference

| Step | Tool | Key param |
|------|------|-----------|
| Mark task done | `TaskUpdate` | `status: completed` |
| Remove worktree | `Bash` — `git worktree remove` | `--force` only if merged |
| Delete local branch | `Bash` — `git branch -d` | never `-D` on unmerged |
| Shutdown agent | `SendMessage` | `type: shutdown_request` |

## Common Mistakes

- **Deleting the branch before the worktree** — always remove the worktree first; git won't let you delete a branch with a live worktree.
- **Skipping task update** — if a task was tracking this work and stays `in_progress`, it pollutes future `TaskList` reads.
- **Forgetting to wait for shutdown_approved** — the agent may still be doing final writes; confirm termination before reporting clean.
