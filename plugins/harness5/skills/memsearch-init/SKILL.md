---
name: memsearch-init
description: Use when setting up memsearch for a new project for the first time — user runs /memsearch-init or wants to enable semantic doc search in the current repo.
---

# /memsearch-init — One-time project setup

When invoked, follow these steps in order. Halt with a clear error if a halt condition is met.

## 1. Find git repo root

Run `git rev-parse --show-toplevel`. Store as `REPO_ROOT`.

**Halt if not in a git repo:**
> **memsearch-init: not in a git repository.** Run this skill from inside a project repo. Aborting.

## 2. Derive collection name

Take the basename of `REPO_ROOT`, lowercase it, replace every non-alphanumeric character with `_`. Store as `COLLECTION`.

Example: `/Users/tony/project/my-cool-app` → `my_cool_app`

## 3. Check for existing config

Check if `<REPO_ROOT>/.memsearch.toml` exists.

- If it exists: read it. Use `collection` value if present (overrides derived name). Use `paths` array if present.
- If missing: default `PATHS` to `["docs/"]`.

## 4. Confirm with user

Present derived values and ask for confirmation before proceeding:

> Ready to index:
> - Collection: `<COLLECTION>`
> - Paths: `<PATHS>`
>
> Proceed? (yes/no)

Wait for confirmation. Apply any corrections to `COLLECTION` and/or `PATHS` before proceeding.

**Halt condition:** `<REPO_ROOT>/docs/` does not exist AND `PATHS` is still `["docs/"]` (no override):
> **memsearch-init: `docs/` directory not found** at `<REPO_ROOT>/docs/`. Either create `docs/` or provide a `paths` override in `.memsearch.toml`. Aborting.

## 5. Run indexer

```
memsearch index <PATHS joined by spaces> -c <COLLECTION>
```

Capture stdout/stderr. If memsearch exits non-zero:
> **memsearch-init: indexing failed.**
> ```
> <raw error output>
> ```
> Hint: run `memsearch config init` to configure your API key, or check `OPENAI_API_KEY`.

## 6. Write config file

Write `<REPO_ROOT>/.memsearch.toml`:

```toml
collection = "<COLLECTION>"
paths = ["<path1>", "..."]
```

## 7. Update .gitignore

Check if `.memsearch.toml` is already covered in `<REPO_ROOT>/.gitignore`. If not, append:

```
.memsearch.toml
```

Add a leading newline if the file does not end with one. Create `.gitignore` if it does not exist.

## 8. Report

> **memsearch-init complete.**
> - Collection: `<COLLECTION>`
> - Paths indexed: `<PATHS>`
> - Config written to: `<REPO_ROOT>/.memsearch.toml`
> - `.gitignore` updated: yes / already present
