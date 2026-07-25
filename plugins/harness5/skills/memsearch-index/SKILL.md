---
name: memsearch-index
description: Use when re-indexing project docs after content changes — user runs /memsearch-index or has added/edited docs since last index.
---

# /memsearch-index — Re-index on demand

When invoked, follow these steps in order.

## 1. Find git repo root

Run `git rev-parse --show-toplevel`. Store as `REPO_ROOT`.

**Halt if not in a git repo:**
> **memsearch-index: not in a git repository.** Aborting.

## 2. Read config

Read `<REPO_ROOT>/.memsearch.toml`. Extract `collection` as `COLLECTION` and `paths` as `PATHS`.

**Halt if missing:**
> **memsearch-index: `.memsearch.toml` not found.** Run /memsearch-init first.

## 3. Re-index

```
memsearch index <PATHS joined by spaces> -c <COLLECTION> --force
```

Capture stdout/stderr. If memsearch exits non-zero, surface the raw error output.

## 4. Report

> **memsearch-index complete.**
> - Collection: `<COLLECTION>`
> - Paths indexed: `<PATHS>`
