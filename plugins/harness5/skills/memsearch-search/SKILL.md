---
name: memsearch-search
description: Use when running a semantic search against indexed project docs — user runs /memsearch-search or the auto-trigger fires on a docs-lookup question.
---

# /memsearch-search — Search and inject results

Takes a `QUERY` argument (required).

When invoked, follow these steps in order.

## 1. Find git repo root

Run `git rev-parse --show-toplevel`. Store as `REPO_ROOT`.

If not in a git repo, emit a one-liner note and continue — do not halt.

## 2. Read config

Check if `<REPO_ROOT>/.memsearch.toml` exists.

- If missing: silently no-op and continue. Do NOT halt — this skill must be safe to auto-trigger in projects without memsearch set up.
- If present: read it. Extract `collection` as `COLLECTION`.

## 3. Run search

```
memsearch search "<QUERY>" -c <COLLECTION> --top-k 5 --json-output
```

If memsearch errors or returns zero results: emit a one-liner note and continue. Do not halt.

## 4. Format and prepend results

Format results as a quoted block:

```
> [memsearch: N results from `<COLLECTION>`]
> - <source-path>: "<excerpt>"
> - <source-path>: "<excerpt>"
```

Prepend this block to your response context before answering the user's question.
