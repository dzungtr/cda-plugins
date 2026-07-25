---
name: harness5-init
description: >
  Initialize the shared harness5 infrastructure stack after installing the plugin. Resolve the
  plugin cache root from the active harness, scaffold infrastructure/.env without overwriting it,
  start Docker Compose, and report the SigNoz URL after its healthcheck.
---

## 1. Resolve the plugin root

Resolve the installed plugin root from the harness-provided environment variables. Check
`PLUGIN_ROOT` first because that is the Codex plugin-root variable. If it is unset or empty, check
`CLAUDE_PLUGIN_ROOT`. Store the first non-empty value as `HARNESS5_PLUGIN_ROOT`:

```bash
if [ -n "${PLUGIN_ROOT:-}" ]; then
  HARNESS5_PLUGIN_ROOT="$PLUGIN_ROOT"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  HARNESS5_PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  printf '%s\n' 'harness5-init: no plugin root found. Run this skill from an installed harness5 plugin (PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT must be set).' >&2
  exit 1
fi
```

Set `INFRA_ROOT` to `<HARNESS5_PLUGIN_ROOT>/infrastructure`. Halt with a clear error if that
directory does not exist:

> **harness5-init: infrastructure directory not found at `<HARNESS5_PLUGIN_ROOT>/infrastructure`.** Run this skill from an installed harness5 plugin. Aborting.

## 2. Scaffold and confirm the environment

Set:

```bash
ENV_EXAMPLE="$INFRA_ROOT/.env.example"
ENV_FILE="$INFRA_ROOT/.env"
```

If `ENV_EXAMPLE` is missing, halt and report its path. If `ENV_FILE` does not exist, copy the
example without overwriting any existing file:

```bash
if [ ! -f "$ENV_FILE" ]; then
  cp -- "$ENV_EXAMPLE" "$ENV_FILE"
fi
```

After copying, tell the user that the new file is at `<HARNESS5_PLUGIN_ROOT>/infrastructure/.env`
and show the assignment lines from the current `.env.example` verbatim. This keeps the complete
key list aligned with the example, including commented optional entries:

```bash
sed -n -E '/^[[:space:]]*#?[A-Z][A-Z0-9_]*=/p' "$ENV_EXAMPLE"
```

Ask the user to fill or review every key shown and explicitly confirm when the secrets and other
values are ready. Do not run Compose until the user confirms. If the user does not confirm, stop
with a message that `harness5-init` was not started. Never overwrite an existing `ENV_FILE`; when
it already exists, continue without copying or asking for a second scaffold confirmation.

## 3. Discover the Compose file and start the stack

Read the Compose filename from the plugin's infrastructure directory instead of assuming a
filename or using the current working directory. There must be exactly one top-level Compose file
matching `*compose*.yml` or `*compose*.yaml`; otherwise halt and report the candidates so the
ambiguous install can be corrected:

```bash
mapfile -t COMPOSE_FILES < <(
  find "$INFRA_ROOT" -maxdepth 1 -type f \
    \( -name '*compose*.yml' -o -name '*compose*.yaml' \) -print | sort
)
if [ "${#COMPOSE_FILES[@]}" -ne 1 ]; then
  printf '%s\n' "harness5-init: expected exactly one Compose file in $INFRA_ROOT; found:" >&2
  printf '  %s\n' "${COMPOSE_FILES[@]}" >&2
  exit 1
fi
COMPOSE_FILE="${COMPOSE_FILES[0]}"
```

Validate the discovered file, then start the stack from the plugin's own infrastructure directory:

```bash
docker compose -f "$COMPOSE_FILE" config >/dev/null
docker compose -f "$COMPOSE_FILE" up -d
```

If either command fails, report the command's error and stop.

## 4. Wait for health and report URLs

Use the discovered Compose file to identify the `signoz` container, then poll its Docker
health status until it is `healthy`. Do not treat `starting` as success. If it becomes `unhealthy`
or the wait times out, report the status and recent container logs, then stop:

```bash
SIGNOZ_CONTAINER_ID="$(docker compose -f "$COMPOSE_FILE" ps -q signoz)"
if [ -z "$SIGNOZ_CONTAINER_ID" ]; then
  printf '%s\n' 'harness5-init: signoz container was not created. Aborting.' >&2
  exit 1
fi

for attempt in $(seq 1 60); do
  HEALTH_STATUS="$(docker inspect --format '{{.State.Health.Status}}' "$SIGNOZ_CONTAINER_ID" 2>/dev/null || true)"
  case "$HEALTH_STATUS" in
    healthy)
      break
      ;;
    unhealthy)
      docker logs --tail 50 "$SIGNOZ_CONTAINER_ID" >&2 || true
      printf '%s\n' 'harness5-init: signoz healthcheck is unhealthy. Aborting.' >&2
      exit 1
      ;;
    *)
      if [ "$attempt" -eq 60 ]; then
        docker logs --tail 50 "$SIGNOZ_CONTAINER_ID" >&2 || true
        printf '%s\n' "harness5-init: timed out waiting for signoz healthcheck (status: ${HEALTH_STATUS:-unknown}). Aborting." >&2
        exit 1
      fi
      sleep 5
      ;;
  esac
done
```

Only after the health status is `healthy`, report:

- SigNoz UI: `http://localhost:8080` (the `signoz` mapping is `${SIGNOZ_UI_PORT:-8080}:8080`; use the configured `SIGNOZ_UI_PORT` value if the user changed it)

If the discovered Compose file has no host-port mapping for the SigNoz UI, report
`http://localhost:3301` with the comment `# default: 3301; no SigNoz UI port is declared in the Compose file.`
