#!/usr/bin/env python3
"""stop hook: hand Cursor's stop event to peon-ping with the assistant's final text as the banner body."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cache_path

PEON_SCRIPT = os.path.expanduser("~/.claude/hooks/peon-ping/peon.sh")


def take_cached_excerpt(conversation_id):
    response_file = cache_path("response", conversation_id)
    if not response_file or not os.path.exists(response_file):
        return ""
    with open(response_file) as handle:
        excerpt = handle.read().strip()
    os.remove(response_file)
    return excerpt


def with_excerpt(raw_event):
    event = json.loads(raw_event)
    conversation_id = event.get("conversation_id") or event.get("session_id") or ""
    event["message"] = take_cached_excerpt(conversation_id) or "Done"
    return json.dumps(event)


raw_event = sys.stdin.read()
try:
    peon_payload = with_excerpt(raw_event)
except Exception:
    peon_payload = raw_event

# Never PIPE peon.sh's stdout: it backgrounds the sound/overlay child, which holds
# the write end open for the full banner dismiss and makes Cursor kill this hook at
# its 60s timeout. peon.sh emits nothing Cursor consumes.
subprocess.run(
    ["bash", PEON_SCRIPT],
    input=peon_payload,
    text=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
