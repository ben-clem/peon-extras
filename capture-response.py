#!/usr/bin/env python3
"""afterAgentResponse hook: stash the assistant's latest text for the stop-hook banner body."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import CACHE_DIR, cache_path, prune_stale_entries

MAX_EXCERPT_CHARS = 160


def to_single_line(assistant_text):
    without_code_fences = re.sub(r"```.*?```", "", assistant_text, flags=re.DOTALL)
    for line in without_code_fences.splitlines():
        condensed = re.sub(r"\s+", " ", line.strip(" #-*>|")).strip()
        if condensed:
            return condensed[:MAX_EXCERPT_CHARS]
    return ""


def store_latest_response():
    event = json.load(sys.stdin)
    conversation_id = event.get("conversation_id") or event.get("session_id") or ""
    response_file = cache_path("response", conversation_id)
    if not response_file:
        return
    excerpt = to_single_line(str(event.get("text") or ""))
    if not excerpt:
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    prune_stale_entries()
    with open(response_file, "w") as handle:
        handle.write(excerpt + "\n")


try:
    store_latest_response()
except Exception:
    pass

print("{}")
