---
name: graphsearch-query
description: Use when running a graph query against indexed codebase relationships — user runs /graphsearch-query or asks about relationships between K8s resources, Terraform modules, or RBAC permissions.
---

# /graphsearch-query — Query the graph

Takes a `QUERY` argument (required). The argument is a named query or `cypher` for raw Cypher.

Named queries available:
- `list-workspaces` — all distinct workspace values
- `blast-radius` — all workloads reachable from a given workload via CAN_REACH edges; params: workspace, env, kind, namespace, name
- `who-can-reach-capability` — workloads that hold a given ApiPermission via RBAC chain; params: resource, verb
- `network-reachability` — all explicit CAN_REACH edges

When invoked, follow these steps in order.

## 1. Find git repo root

Run `git rev-parse --show-toplevel`. Store as `REPO_ROOT`.

If not in a git repo, emit a one-liner note and continue — do not halt.

## 2. Read config

Check if `<REPO_ROOT>/.graphsearch.toml` exists.

- If missing: silently no-op and continue. Do NOT halt — this skill must be safe to call in projects without graphsearch set up.
- If present: read it. Extract `workspace` as `WORKSPACE`.

## 3. Run query

For named queries:
```
graphsearch query <QUERY> [--param key=value ...] [--json-output]
```

For raw Cypher:
```
graphsearch query cypher --cypher "<CYPHER>" [--json-output]
```

Examples:
```bash
graphsearch query list-workspaces
graphsearch query blast-radius --param workspace=my-repo --param env=prod --param kind=Deployment --param namespace=default --param name=api
graphsearch query who-can-reach-capability --param resource=secrets --param verb=get
graphsearch query network-reachability --json-output
graphsearch query cypher --cypher "MATCH (n:K8sResource) RETURN n.name LIMIT 10"
```

If graphsearch errors or returns zero results: emit a one-liner note and continue. Do not halt.

## 4. Format and prepend results

Format results as a quoted block:

```
> [graphsearch: N results from workspace `<WORKSPACE>`]
> - <row contents>
> - ...
```

Prepend this block to your response context before answering the user's question.
