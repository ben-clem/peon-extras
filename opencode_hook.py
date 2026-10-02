#!/usr/bin/env python3
"""Bridge normalized OpenCode V2 events to peon.sh and compaction banners."""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import CACHE_DIR, cache_path, prune_stale_entries
from _usage import usage_line

DEFAULT_PEON_DIR = "~/.claude/hooks/peon-ping"
TITLE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notification_title.py")
FALLBACK_COMPACT_BODY = "Summarizing this chat now"


def peon_dir():
    return os.path.expanduser(os.environ.get("PEON_DIR", DEFAULT_PEON_DIR))


def event_environment(event):
    env = os.environ.copy()
    env.update(
        {
            "PEON_DIR": peon_dir(),
            "CLAUDE_PEON_DIR": peon_dir(),
            "PEON_IDE": "opencode",
            "PEON_SESSION_ID": str(event.get("session_id") or ""),
            "PEON_CWD": str(event.get("cwd") or ""),
            "PEON_CHAT_TITLE": str(event.get("title") or ""),
        }
    )
    return env


def usage_percent(event):
    try:
        percent = float(event.get("context_usage_percent"))
        if percent >= 0:
            return percent
    except (TypeError, ValueError):
        pass
    try:
        tokens = float(event.get("context_tokens"))
        window = float(event.get("context_window_size"))
    except (TypeError, ValueError):
        return None
    if tokens < 0 or window <= 0:
        return None
    return tokens * 100.0 / window


def usage_banner(event, prefix):
    return usage_line(
        prefix,
        event.get("context_tokens"),
        event.get("context_window_size"),
        usage_percent(event),
    )


def store_compact_body(event):
    path = cache_path("compact-body", event.get("session_id"))
    if not path:
        return
    message = usage_banner(event, "Summarizing") or FALLBACK_COMPACT_BODY
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        prune_stale_entries()
        with open(path, "w") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def run_peon(event):
    script = os.path.join(peon_dir(), "peon.sh")
    if not os.path.isfile(script):
        return 0
    payload = dict(event)
    payload["source"] = "opencode"
    return subprocess.run(
        ["bash", script],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        env=event_environment(event),
    ).returncode


def prime_title(event, env):
    try:
        result = subprocess.run(
            [sys.executable, TITLE_SCRIPT],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()[:50] if result.returncode == 0 else ""


def send_after_compact(event, message):
    env = event_environment(event)
    title = prime_title(event, env)
    if not title:
        title = Path(str(event.get("cwd") or "OpenCode")).name or "OpenCode"
    script = os.path.join(peon_dir(), "scripts", "notify.sh")
    if not os.path.isfile(script):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify-banner-title.sh")
    if not os.path.isfile(script):
        return
    env.update({"PEON_SYNC": "1", "PEON_PLATFORM": "mac"})
    subprocess.run(
        ["bash", script, message, title, "blue"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def handle_event(event, peon_runner=None, banner_sender=None):
    payload = dict(event)
    payload["source"] = "opencode"
    name = payload.get("hook_event_name")
    if name == "PreCompact":
        store_compact_body(payload)
        runner = peon_runner or run_peon
        return runner(payload)
    if name == "PostCompact":
        message = usage_banner(payload, "Done summarizing") or "Done summarizing this chat"
        sender = banner_sender or send_after_compact
        sender(payload, message)
        return 0
    runner = peon_runner or run_peon
    return runner(payload)


def main():
    try:
        event = json.load(sys.stdin)
    except (TypeError, ValueError):
        return 0
    if not isinstance(event, dict):
        return 0
    return handle_event(event)


if __name__ == "__main__":
    sys.exit(main())
