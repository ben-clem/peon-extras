#!/usr/bin/env python3
"""Translate Codex hooks into PeonPing events and richer banners."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import CACHE_DIR, cache_path, prune_stale_entries
from _usage import usage_line
from precompact import send_after_banner

PEON_DIR = os.path.expanduser(
    os.environ.get("PEON_DIR", "~/.claude/hooks/peon-ping")
)
PEON_SCRIPT = os.path.join(PEON_DIR, "peon.sh")
CODEX_ADAPTER = os.path.join(PEON_DIR, "adapters", "codex.sh")
TITLE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notification_title.py")
MAX_TRANSCRIPT_TAIL = 8 * 1024 * 1024


def clean_line(value, limit=160):
    return " ".join(str(value or "").split()).strip()[:limit]


def session_id(event):
    raw = clean_line(
        event.get("session_id")
        or event.get("conversation_id")
        or event.get("thread_id"),
        100,
    )
    if not raw:
        raw = str(os.getpid())
    return raw if raw.startswith("codex-") else "codex-{}".format(raw)


def question_message(event):
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return "Question pending"
    questions = tool_input.get("questions")
    if not isinstance(questions, list) or not questions:
        return "Question pending"
    first = questions[0]
    if not isinstance(first, dict):
        return "Question pending"
    question = clean_line(first.get("question"))
    header = clean_line(first.get("header"), 40)
    if question:
        return question
    if header:
        return "{} question pending".format(header)
    return "Question pending"


def question_payload(event):
    return {
        "hook_event_name": "Notification",
        "notification_type": "elicitation_dialog",
        "message": question_message(event),
        "tool_name": "request_user_input",
        "cwd": str(event.get("cwd") or os.environ.get("PWD") or "/"),
        "session_id": session_id(event),
        "source": "codex",
    }


def transcript_tail(path, byte_limit=MAX_TRANSCRIPT_TAIL):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - byte_limit)
            handle.seek(start)
            data = handle.read()
    except OSError:
        return []
    if start:
        first_newline = data.find(b"\n")
        data = data[first_newline + 1 :] if first_newline >= 0 else b""
    return data.decode("utf-8", "replace").splitlines()


def latest_context_usage(path):
    if not path:
        return None
    for line in reversed(transcript_tail(path)):
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        usage = info.get("last_token_usage")
        if not isinstance(usage, dict):
            continue
        try:
            used = int(usage.get("total_tokens"))
            window = int(info.get("model_context_window"))
        except (TypeError, ValueError):
            continue
        if used < 0 or window <= 0:
            continue
        return used, window, used * 100.0 / window
    return None


def write_compact_body(event):
    usage = latest_context_usage(str(event.get("transcript_path") or ""))
    body = usage_line("Summarizing", *usage) if usage else "Summarizing this chat now"
    path = cache_path("compact-body", session_id(event))
    if not path:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        prune_stale_entries()
        with open(path, "w") as handle:
            handle.write(body + "\n")
    except OSError:
        pass


def prime_title(event):
    env = os.environ.copy()
    env.update(
        {
            "PEON_IDE": "codex",
            "PEON_SESSION_ID": session_id(event),
            "PEON_CWD": str(event.get("cwd") or ""),
        }
    )
    subprocess.run(
        [sys.executable, TITLE_SCRIPT],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def send_postcompact(event):
    usage = latest_context_usage(str(event.get("transcript_path") or ""))
    body = (
        usage_line("Done summarizing", *usage)
        if usage
        else "Done summarizing this chat"
    )
    prime_title(event)
    send_after_banner(session_id(event), body)


def run_peon(payload):
    if not os.path.isfile(PEON_SCRIPT):
        return 0
    completed = subprocess.run(
        ["bash", PEON_SCRIPT],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode


def run_adapter(raw):
    if not os.path.isfile(CODEX_ADAPTER):
        return 0
    completed = subprocess.run(
        ["bash", CODEX_ADAPTER],
        input=raw,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except (TypeError, ValueError):
        event = {}
    if not isinstance(event, dict):
        event = {}

    transcript_path = str(event.get("transcript_path") or "")
    if transcript_path:
        os.environ["PEON_TRANSCRIPT_PATH"] = transcript_path

    name = clean_line(event.get("hook_event_name"), 40)
    if name == "PreToolUse":
        if event.get("tool_name") != "request_user_input":
            return 0
        return run_peon(question_payload(event))
    if name == "PreCompact":
        write_compact_body(event)
        return run_adapter(raw)
    if name == "PostCompact":
        send_postcompact(event)
        return 0
    return run_adapter(raw)


if __name__ == "__main__":
    sys.exit(main())
