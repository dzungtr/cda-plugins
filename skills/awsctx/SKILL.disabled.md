---
name: awsctx
description: Use when AWS credentials are expired, missing, or a new AWS session token is needed before running AWS CLI commands, terraform, kubectl with AWS auth, or any AWS-authenticated operation.
---

# awsctx — AWS SSO Session Login

## Overview

Acquire a fresh AWS SSO session before any AWS-authenticated operation. The profile name determines which AWS account and role are targeted — **a wrong profile can provision resources in the wrong environment or account, which may be irreversible.**

## When to Use

- AWS CLI returns `ExpiredToken`, `NoCredentialProviders`, or `Unable to locate credentials`
- Terraform plan/apply fails with an AWS auth error
- kubectl (EKS) fails due to expired AWS token
- Any task requires AWS access and no valid session exists

## Profile Identification

**This step is critical. Do not guess carelessly.**

```
digraph profile_id {
    "Need AWS profile" [shape=doublecircle];
    "Scan conversation history" [shape=box];
    "100% confident?" [shape=diamond];
    "Use that profile" [shape=box];
    "ASK THE USER" [shape=box, style=filled, fillcolor=lightyellow];
    "Run aws sso login" [shape=box];

    "Need AWS profile" -> "Scan conversation history";
    "Scan conversation history" -> "100% confident?" ;
    "100% confident?" -> "Use that profile" [label="yes"];
    "100% confident?" -> "ASK THE USER" [label="no / unsure"];
    "Use that profile" -> "Run aws sso login";
    "ASK THE USER" -> "Run aws sso login";
}
```

**Signals that raise confidence:**
- User explicitly stated a profile name in this conversation (e.g., `--profile sandbox`, `profile: primary-eks`)
- A `~/.aws/config` or `~/.aws/credentials` file was shown with a single obvious match
- The task context unambiguously maps to one environment (e.g., "sandbox terraform plan" → sandbox profile)

**When in doubt, ask.** One prompt is far cheaper than provisioning resources in the wrong account.

Example question to ask:
> Which AWS profile should I use? (e.g., `sandbox`, `primary-eks`, `oolio-prod`?)

## Command

```bash
aws sso login --profile <profile>
```

After login, verify the session is active:

```bash
aws sts get-caller-identity --profile <profile>
```

The output confirms the Account ID and Role — show this to the user so they can verify it's the intended target before proceeding.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Assuming the default profile is correct | Always confirm profile from context or ask |
| Skipping `sts get-caller-identity` verification | Always verify — account ID confirms you're in the right environment |
| Re-using a profile name from a past session without checking | Conversation context changes; re-confirm each session |
| Proceeding after a partial/failed SSO login | Check exit code; a browser tab must complete the OAuth flow |

## Safety Rule

**Never proceed with AWS operations until `sts get-caller-identity` confirms the correct account.** If the account ID is unexpected, stop and ask the user before continuing.
