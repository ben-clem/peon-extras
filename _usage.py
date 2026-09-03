"""Context-window numbers for summarize banners. Read-only SQLite for the after value."""

import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

STATE_DB = Path(
    os.environ.get(
        "CURSOR_STATE_DB",
        "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
    )
).expanduser()

STOCK_PRECOMPACT_BODY = "compacting: Context compacting"


def format_k(count):
    """287103 -> 287.1K; 300000 -> 300K; 999 -> 999."""
    try:
        value = float(count)
    except (TypeError, ValueError):
        return ""
    if value < 0:
        return ""
    if value >= 1000:
        thousands = value / 1000.0
        if abs(thousands - round(thousands)) < 0.05:
            return "{:.0f}K".format(int(round(thousands)))
        return "{:.1f}K".format(thousands)
    return str(int(round(value)))


def format_percent(value):
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return ""


def usage_line(prefix, used_tokens, window_tokens, percent):
    used = format_k(used_tokens)
    window = format_k(window_tokens)
    pct = format_percent(percent)
    if not used or not window or not pct:
        return ""
    return "{}: {} / {} Tokens ({}% Full)".format(prefix, used, window, pct)


def parse_json(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _percent_from_record(record):
    if not isinstance(record, dict):
        return None
    raw = record.get("contextUsagePercent")
    if raw is None:
        raw = record.get("context_usage_percent")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def usage_percent_from_db(conversation_id):
    """Current composerHeaders.contextUsagePercent, or None if unread."""
    if not conversation_id or not STATE_DB.is_file():
        return None
    database_uri = "file:{}?mode=ro".format(quote(str(STATE_DB), safe=""))
    try:
        connection = sqlite3.connect(database_uri, uri=True, timeout=0.5)
    except sqlite3.Error:
        return None
    try:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute(
            'SELECT value FROM "composerHeaders" WHERE "composerId"=?',
            (conversation_id,),
        ).fetchone()
        if not row:
            return None
        return _percent_from_record(parse_json(row[0]))
    except sqlite3.Error:
        return None
    finally:
        connection.close()
