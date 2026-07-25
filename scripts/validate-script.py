#!/usr/bin/env python3
"""
PreToolUse hook: validates Python/Node.js scripts for suspicious patterns.
Auto-approves clean scripts, blocks suspicious ones.
Non-script commands pass through unchanged (no JSON output, exit 0).
"""
import json
import sys
import re
import os

# Patterns that indicate potentially dangerous Python code
SUSPICIOUS_PYTHON = [
    (r'os\.system\s*\(', "os.system() - arbitrary shell execution"),
    (r'subprocess\.(call|run|Popen|check_output|check_call)\s*\(', "subprocess - shell execution"),
    (r'\beval\s*\(', "eval() - dynamic code execution"),
    (r'\bexec\s*\(', "exec() - dynamic code execution"),
    (r'__import__\s*\(', "__import__() - dynamic import"),
    (r'compile\s*\(.*,\s*[\'"]exec[\'"]\)', "compile(..., 'exec') - dynamic code"),
    (r'base64\b.*\bdecode\b.*\beval\b', "base64 decode + eval - obfuscated execution"),
    (r'base64\b.*\bdecode\b.*\bexec\b', "base64 decode + exec - obfuscated execution"),
    (r'socket\.connect\s*\(', "socket.connect() - outbound network connection"),
    (r'pty\.spawn\s*\(', "pty.spawn() - pseudo-terminal shell"),
    (r'ctypes\.cdll\b', "ctypes - native library loading"),
    (r'pickle\.loads?\s*\(', "pickle.load - arbitrary deserialization"),
    (r'/etc/shadow', "access to /etc/shadow - shadow passwords"),
    (r'/etc/passwd', "access to /etc/passwd - user accounts"),
    (r'~\/\.ssh', "access to ~/.ssh - SSH keys"),
    (r'\.ssh/id_', "access to SSH private keys"),
    (r'shutil\.rmtree\s*\(\s*[\'"/]', "shutil.rmtree on absolute/root path"),
    (r'requests\.(get|post)\s*\(.*shell=True', "requests with shell=True"),
]

# Patterns that indicate potentially dangerous Node.js code
SUSPICIOUS_NODE = [
    (r'child_process\s*\.\s*(exec|execSync|spawn|spawnSync|execFile)\s*\(', "child_process exec - shell execution"),
    (r'require\s*\(\s*[\'"]child_process[\'"]\s*\)', "require('child_process') - shell access"),
    (r'\beval\s*\(', "eval() - dynamic code execution"),
    (r'new\s+Function\s*\(', "new Function() - dynamic code execution"),
    (r'vm\s*\.\s*(runInThisContext|runInNewContext|runInContext)\s*\(', "vm.runIn* - sandboxed eval"),
    (r'process\s*\.\s*binding\s*\(', "process.binding() - native binding access"),
    (r'require\s*\(\s*[\'"]fs[\'"]\s*\).*\.(unlink|rmdir|rm)\s*\(', "fs delete operations"),
    (r'Buffer\.from\s*\(.*,\s*[\'"]base64[\'"]\s*\)', "Buffer base64 decode - potential obfuscation"),
    (r'\.exec\s*\(\s*`', "template literal exec - injection risk"),
    (r'/etc/shadow', "access to /etc/shadow - shadow passwords"),
    (r'/etc/passwd', "access to /etc/passwd - user accounts"),
    (r'~\/\.ssh|\.ssh\/id_', "access to SSH keys"),
    (r'require\s*\(\s*[\'"]net[\'"]\s*\)', "require('net') - raw network socket"),
    (r'require\s*\(\s*[\'"]dgram[\'"]\s*\)', "require('dgram') - UDP socket"),
]


# Patterns flagging AWS SDK usage — prompt for review (ask, not deny)
REVIEW_PYTHON = [
    (r'\bimport boto3\b', "boto3 AWS SDK import"),
    (r'\bfrom boto3\b', "boto3 AWS SDK import"),
    (r'\bimport botocore\b', "botocore import"),
    (r'boto3\s*\.\s*(client|resource|Session)\s*\(', "boto3 client/resource instantiation"),
]

REVIEW_NODE = [
    (r"require\s*\(\s*['\"]aws-sdk['\"]\s*\)", "aws-sdk (v2) require"),
    (r"require\s*\(\s*['\"]@aws-sdk/", "AWS SDK v3 require"),
    (r"from\s+['\"]@aws-sdk/", "AWS SDK v3 import"),
    (r'import\s+\S.*\s+from\s+[\'"]aws-sdk[\'"]', "aws-sdk import"),
]


def check_content(content: str, patterns: list) -> list[str]:
    findings = []
    for pattern, description in patterns:
        if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
            findings.append(description)
    return findings


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")

    # Match inline: python -c "..." / python3 -c "..." / node -e "..."
    py_inline = re.match(r'python3?\s+(?:\S+\s+)*-c\s+(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\')(.*)$', command, re.DOTALL)
    node_inline = re.match(r'node\s+(?:\S+\s+)*-e\s+(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\')(.*)$', command, re.DOTALL)

    # Match file: python/python3/node running a .py/.js file
    py_match = re.match(r'python3?\s+("?)(\S+\.py)\1', command)
    node_match = re.match(r'node\s+("?)(\S+\.js)\1', command)

    if py_inline or node_inline:
        m = py_inline or node_inline
        content = m.group(1) if m.group(1) is not None else m.group(2)
        label = "<inline script>"
        patterns = SUSPICIOUS_PYTHON if py_inline else SUSPICIOUS_NODE
        review_patterns = REVIEW_PYTHON if py_inline else REVIEW_NODE
    elif py_match or node_match:
        match = py_match or node_match
        script_file = os.path.expanduser(match.group(2))
        if not os.path.isfile(script_file):
            sys.exit(0)
        try:
            with open(script_file, "r", errors="replace") as f:
                content = f.read()
        except Exception:
            sys.exit(0)
        label = script_file
        patterns = SUSPICIOUS_PYTHON if py_match else SUSPICIOUS_NODE
        review_patterns = REVIEW_PYTHON if py_match else REVIEW_NODE
    else:
        sys.exit(0)

    findings = check_content(content, patterns)
    review_findings = check_content(content, review_patterns)

    if findings:
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Security validation blocked '{label}': {'; '.join(findings)}",
            },
            "reason": f"Suspicious patterns in {label}: {'; '.join(findings)}",
        }
    elif review_findings:
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": f"AWS SDK usage in '{label}': {'; '.join(review_findings)}. Script may interact with AWS resources — review before running.",
            }
        }
    else:
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": f"'{label}' passed security validation — no suspicious patterns found",
            }
        }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
