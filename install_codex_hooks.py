#!/usr/bin/env python3
"""Idempotently merge peon-extras command hooks into Codex hooks.json."""

import json
import os
import sys
import tempfile

PEON_NEEDLES = ("peon-ping", "peon-extras", "codex_hook.py", "codex.sh")
HOOKS = (
    ("SessionStart", "^(startup|resume|clear)$", 10),
    ("SessionEnd", None, 3),
    ("UserPromptSubmit", None, 10),
    ("PermissionRequest", None, 10),
    ("PreToolUse", "^request_user_input$", 10),
    ("PreCompact", None, 10),
    ("PostCompact", None, 10),
    ("SubagentStart", None, 10),
    ("SubagentStop", None, 10),
    ("Stop", None, 10),
)


def load(path):
    if not os.path.isfile(path):
        return {"hooks": {}}
    with open(path) as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Codex hooks.json must contain an object")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Codex hooks.json 'hooks' must contain an object")
    return data


def is_peon_rule(rule):
    if not isinstance(rule, dict):
        return False
    for handler in rule.get("hooks", []):
        if not isinstance(handler, dict):
            continue
        command = str(handler.get("command") or "")
        if any(needle in command for needle in PEON_NEEDLES):
            return True
    return False


def command_for(dest):
    path = os.path.join(dest, "codex_hook.py")
    return "python3 {}".format(json.dumps(path))


def hook_rule(dest, matcher, timeout):
    rule = {
        "hooks": [
            {
                "type": "command",
                "command": command_for(dest),
                "timeout": timeout,
            }
        ]
    }
    if matcher:
        rule["matcher"] = matcher
    return rule


def merge(data, dest):
    hooks = data.setdefault("hooks", {})
    for event, matcher, timeout in HOOKS:
        current = hooks.get(event, [])
        if not isinstance(current, list):
            current = []
        kept = [rule for rule in current if not is_peon_rule(rule)]
        kept.append(hook_rule(dest, matcher, timeout))
        hooks[event] = kept
    return data


def write_atomic(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".hooks.", dir=directory)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def main(argv):
    if len(argv) != 3:
        print("usage: install_codex_hooks.py HOOKS_JSON RUNTIME_DIR", file=sys.stderr)
        return 2
    hooks_path, dest = argv[1], os.path.abspath(argv[2])
    write_atomic(hooks_path, merge(load(hooks_path), dest))
    print("wrote", hooks_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
