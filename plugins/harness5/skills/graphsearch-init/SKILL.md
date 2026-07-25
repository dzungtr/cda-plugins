---
name: graphsearch-init
description: Use when setting up graphsearch for a new project for the first time — user runs /graphsearch-init or wants to enable graph-based codebase indexing in the current repo.
---

# /graphsearch-init — One-time project setup

When invoked, follow these steps in order. Halt with a clear error if a halt condition is met.

## 1. Find git repo root

Run `git rev-parse --show-toplevel`. Store as `REPO_ROOT`.

**Halt if not in a git repo:**
> **graphsearch-init: not in a git repository.** Run this skill from inside a project repo. Aborting.

## 2. Check for existing config

Check if `<REPO_ROOT>/.graphsearch.toml` exists.

- If it exists: report that config is already present and skip init.
  > **graphsearch-init: .graphsearch.toml already exists at `<REPO_ROOT>/.graphsearch.toml`.** Delete it first if you want to reinitialise.

## 3. Run init

```
graphsearch init
```

This prompts for workspace name, bolt_uri, k8s_overlays, and terraform_roots.
The command refuses to clobber an existing config file.

If graphsearch exits non-zero:
> **graphsearch-init: init failed.**
> ```
> <raw error output>
> ```
> Hint: ensure `graphsearch` is installed via `pipx install graphsearch` or `pip install -e graphsearch/`.

## 4. Report

> **graphsearch-init complete.**
> - Config written to: `<REPO_ROOT>/.graphsearch.toml`
> - Run `graphsearch index` to index this workspace into Memgraph.
