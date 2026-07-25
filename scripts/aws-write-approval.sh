#!/usr/bin/env bash
# PreToolUse hook: prompt approval for AWS write/modify CLI operations.
# Services: dynamodb, s3, s3api, sqs, sns, events, eventbridge
# Read-only operations (describe/list/get) pass through (exit 0, no JSON).
set -euo pipefail

input=$(cat)
command=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')

# Bail if no aws invocation in the command
if ! echo "$command" | grep -qE '(^|[[:space:]])aws[[:space:]]'; then
  exit 0
fi

# Extract the substring starting from 'aws ', strip leading 'aws '
aws_args=$(echo "$command" | grep -oE 'aws[[:space:]]+.*' | head -1 | sed 's/^aws[[:space:]]*//')

# Strip common global options that take a value argument
cleaned=$(echo "$aws_args" \
  | sed -E 's/--profile[[:space:]]+[^[:space:]]+//g' \
  | sed -E 's/--region[[:space:]]+[^[:space:]]+//g' \
  | sed -E 's/--endpoint-url[[:space:]]+[^[:space:]]+//g' \
  | sed -E 's/--output[[:space:]]+[^[:space:]]+//g' \
  | sed -E 's/--query[[:space:]]+[^[:space:]]+//g' \
  | sed -E 's/--color[[:space:]]+[^[:space:]]+//g' \
  | sed -E 's/--no-verify-ssl//g' \
  | sed -E 's/--debug//g' \
  | tr -s ' ' \
  | sed 's/^[[:space:]]*//')

service=$(echo "$cleaned" | awk '{print $1}')
operation=$(echo "$cleaned" | awk '{print $2}')

if [[ -z "$service" || -z "$operation" ]]; then
  exit 0
fi

# Write/modify operation lists per service
case "$service" in
  dynamodb)
    write_ops="put-item|delete-item|update-item|batch-write-item|transact-write-items|create-table|delete-table|update-table|create-backup|delete-backup|restore-table-from-backup|restore-table-to-point-in-time|put-resource-policy|delete-resource-policy|tag-resource|untag-resource|update-continuous-backups|update-global-table|update-global-table-settings|update-time-to-live"
    ;;
  s3)
    write_ops="cp|mv|rm|sync|mb|rb|website|presign"
    ;;
  s3api)
    write_ops="put-object|delete-object|delete-objects|create-bucket|delete-bucket|put-bucket-acl|put-bucket-cors|put-bucket-encryption|put-bucket-lifecycle-configuration|put-bucket-logging|put-bucket-notification-configuration|put-bucket-policy|put-bucket-replication|put-bucket-request-payment|put-bucket-tagging|put-bucket-versioning|put-bucket-website|put-object-acl|put-object-legal-hold|put-object-lock-configuration|put-object-retention|put-object-tagging|put-public-access-block|delete-bucket-analytics-configuration|delete-bucket-cors|delete-bucket-encryption|delete-bucket-intelligent-tiering-configuration|delete-bucket-lifecycle|delete-bucket-metrics-configuration|delete-bucket-ownership-controls|delete-bucket-policy|delete-bucket-replication|delete-bucket-tagging|delete-bucket-website|delete-object-tagging|delete-public-access-block|copy-object|restore-object|complete-multipart-upload|upload-part|upload-part-copy"
    ;;
  sqs)
    write_ops="create-queue|delete-queue|send-message|send-message-batch|delete-message|delete-message-batch|change-message-visibility|change-message-visibility-batch|set-queue-attributes|purge-queue|add-permission|remove-permission|tag-queue|untag-queue"
    ;;
  sns)
    write_ops="create-topic|delete-topic|publish|publish-batch|subscribe|unsubscribe|set-topic-attributes|set-subscription-attributes|confirm-subscription|add-permission|remove-permission|create-platform-application|delete-platform-application|set-platform-application-attributes|create-platform-endpoint|delete-endpoint|set-endpoint-attributes|set-sms-attributes|tag-resource|untag-resource|opt-in-phone-number"
    ;;
  events|eventbridge)
    write_ops="put-events|put-partner-events|create-event-bus|delete-event-bus|put-rule|delete-rule|put-targets|remove-targets|enable-rule|disable-rule|create-connection|delete-connection|update-connection|create-api-destination|delete-api-destination|update-api-destination|put-permission|remove-permission|create-archive|delete-archive|update-archive|create-replay|cancel-replay|tag-resource|untag-resource|create-endpoint|delete-endpoint|update-endpoint"
    ;;
  secretsmanager)
    write_ops="create-secret|delete-secret|restore-secret|update-secret|put-secret-value|rotate-secret|cancel-rotate-secret|update-secret-version-stage|put-resource-policy|delete-resource-policy|replicate-secret-to-regions|remove-regions-from-replication|stop-replication-to-replica|tag-resource|untag-resource"
    ;;
  *)
    exit 0
    ;;
esac

if echo "$operation" | grep -qE "^($write_ops)$"; then
  reason="AWS write/modify: aws ${service} ${operation} — modifies live AWS resources. Explicit approval required."
  jq -n --arg r "$reason" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "ask",
      permissionDecisionReason: $r
    }
  }'
else
  # Read-only or unrecognised operation — pass through
  exit 0
fi
