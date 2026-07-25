---
name: graphsearch-index
description: Use when indexing or re-indexing a workspace into the Memgraph graph — user runs /graphsearch-index or has added/changed infra or K8s manifests since last index.
---

# /graphsearch-index — Index or re-index the workspace

When invoked, follow these steps in order.

## 1. Find git repo root

Run `git rev-parse --show-toplevel`. Store as `REPO_ROOT`.

**Halt if not in a git repo:**
> **graphsearch-index: not in a git repository.** Aborting.

## 2. Read config

Check if `<REPO_ROOT>/.graphsearch.toml` exists.

**Halt if missing:**
> **graphsearch-index: `.graphsearch.toml` not found.** Run /graphsearch-init first.

Read it. Extract `workspace` as `WORKSPACE`.

## 3. Confirm Memgraph is reachable

Verify the Memgraph compose service is running:

```
docker compose -f infrastructure/docker-compose.yml ps memgraph
```

If not running:
> **graphsearch-index: Memgraph is not running.** Start it with:
> ```
> docker compose -f infrastructure/docker-compose.yml up -d memgraph
> ```

## 4. Run indexer

```
graphsearch index
```

Capture stdout/stderr. If graphsearch exits non-zero, surface the raw error output.

## 5. Report

> **graphsearch-index complete.**
> - Workspace: `<WORKSPACE>`
