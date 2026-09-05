#!/usr/bin/env python3
"""preCompact hook: before/after summarize banners, then peon.sh for the sound.

Cursor has no postCompact hook. After the before banner, a detached watcher
polls composerHeaders.contextUsagePercent until it drops, then shows the after
line. Before numbers come from the hook payload (exact tokens). After tokens
are estimated as percent * window / 100.
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import CACHE_DIR, cache_path, prune_stale_entries
from _usage import usage_line, usage_percent_from_db

PEON_DIR = os.path.expanduser(
    os.environ.get("PEON_DIR", "~/.claude/hooks/peon-ping")
)
PEON_SCRIPT = os.path.join(PEON_DIR, "peon.sh")
NOTIFY_SCRIPT = os.path.join(PEON_DIR, "scripts", "notify.sh")
DROP_POINTS = 5.0
POLL_SECONDS = 1.0
TIMEOUT_SECONDS = 300
WATCH_KIND = "summarize-watch"
BODY_KIND = "compact-body"


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value):
    number = _as_float(value)
    if number is None:
        return None
    return int(round(number))


def write_text(path, text):
    if not path:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    prune_stale_entries()
    with open(path, "w") as handle:
        handle.write(text)


def load_watch(path):
    try:
        with open(path) as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def banner_title_args(conversation_id):
    path = cache_path("banner-title", conversation_id)
    if not path or not os.path.isfile(path):
        return "peon-ping"
    try:
        with open(path) as handle:
            match_title = handle.readline().rstrip("\n")
    except OSError:
        return "peon-ping"
    return match_title or "peon-ping"


def send_after_banner(conversation_id, message):
    if not message or not os.path.isfile(NOTIFY_SCRIPT):
        return
    env = os.environ.copy()
    env["PEON_DIR"] = PEON_DIR
    env["PEON_SESSION_ID"] = conversation_id
    env["PEON_SYNC"] = "1"
    env["PEON_PLATFORM"] = "mac"
    subprocess.run(
        ["bash", NOTIFY_SCRIPT, message, banner_title_args(conversation_id), "blue"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def watch_main(watch_path, generation):
    payload = load_watch(watch_path)
    conversation_id = str(payload.get("conversation_id") or "")
    before_percent = _as_float(payload.get("before_percent"))
    window = _as_int(payload.get("window_size"))
    if not conversation_id or before_percent is None or not window:
        return 0

    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        latest = load_watch(watch_path)
        if latest.get("generation") != generation:
            return 0
        current = usage_percent_from_db(conversation_id)
        if current is None:
            continue
        if current <= before_percent - DROP_POINTS:
            used = window * current / 100.0
            message = usage_line("Done summarizing", used, window, current)
            if message:
                send_after_banner(conversation_id, message)
            try:
                os.remove(watch_path)
            except OSError:
                pass
            return 0
    return 0


def store_before(conversation_id, event):
    percent = _as_float(event.get("context_usage_percent"))
    tokens = _as_int(event.get("context_tokens"))
    window = _as_int(event.get("context_window_size"))
    body = usage_line("Summarizing", tokens, window, percent)
    if not body:
        body = "Summarizing this chat now"
    write_text(cache_path(BODY_KIND, conversation_id), body + "\n")
    if percent is None or not window:
        return
    watch_path = cache_path(WATCH_KIND, conversation_id)
    previous = load_watch(watch_path)
    generation = int(previous.get("generation") or 0) + 1
    snapshot = {
        "conversation_id": conversation_id,
        "before_percent": percent,
        "window_size": window,
        "before_tokens": tokens,
        "generation": generation,
    }
    write_text(watch_path, json.dumps(snapshot) + "\n")
    subprocess.Popen(
        [
            sys.executable,
            os.path.abspath(__file__),
            "--watch",
            watch_path,
            str(generation),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def hook_main():
    raw_event = sys.stdin.read()
    conversation_id = ""
    try:
        event = json.loads(raw_event)
        conversation_id = event.get("conversation_id") or event.get("session_id") or ""
        store_before(conversation_id, event)
    except Exception:
        pass

    # Never PIPE peon.sh's stdout: it backgrounds the sound/overlay child, which
    # holds the write end open for the full banner dismiss and makes Cursor kill
    # this hook at its 60s timeout. peon.sh emits nothing Cursor consumes.
    completed = subprocess.run(
        ["bash", PEON_SCRIPT],
        input=raw_event,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--watch":
        sys.exit(watch_main(sys.argv[2], int(sys.argv[3])))
    sys.exit(hook_main())
