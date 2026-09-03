"""Shared cache locations for the Cursor-side peon-ping hook helpers."""

import os
import re
import time

CACHE_DIR = os.path.expanduser("~/.cursor/peon-extras/cache")
CACHE_TTL_DAYS = 14


def cache_path(kind, conversation_id):
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(conversation_id))[:64]
    if not safe_id:
        return ""
    return os.path.join(CACHE_DIR, "{}-{}".format(kind, safe_id))


def prune_stale_entries():
    cutoff = time.time() - CACHE_TTL_DAYS * 86400
    try:
        entries = os.listdir(CACHE_DIR)
    except OSError:
        return
    for name in entries:
        path = os.path.join(CACHE_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass
