#!/usr/bin/env python3
"""Build a PeonPing title from Cursor's read-only chat metadata.

Prints `<workspace> > <chat-title>`. peon-ping then strips `>` from that
label, so the notify wrapper matches the sanitized form and restores either
the emoji banner or this `>` fallback.
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import CACHE_DIR, cache_path, prune_stale_entries

MAX_TITLE_CHARS = 50
MAX_WORKSPACE_CHARS = 20
HOME_WORKSPACE_LABEL = "Home"
PLAIN_SEPARATOR = " > "
BANNER_FORMAT = "\U0001f4c2 {} \U0001f4ac {}"
# Match peon.sh's final project sanitizer (`[^a-zA-Z0-9 ._-]`). A looser set
# (comma, etc.) makes the notify wrapper miss $2 and skip the emoji title.
PEON_TITLE_CHARS = re.compile(r"[^A-Za-z0-9 ._-]")
STATE_DB = Path(
    os.environ.get(
        "CURSOR_STATE_DB",
        "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
    )
).expanduser()


def parse_json(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def clean_label(value):
    return " ".join(str(value or "").split()).strip()


def title_from_record(record, conversation_id):
    if not isinstance(record, dict):
        return ""

    record_id = clean_label(
        record.get("composerId")
        or record.get("conversationId")
        or record.get("id")
    )
    if not record_id or record_id == conversation_id:
        title = clean_label(record.get("name") or record.get("title"))
        if title:
            return title

    for container_name in ("allComposers", "composers", "headers"):
        container = record.get(container_name)
        if isinstance(container, list):
            for item in container:
                title = title_from_record(item, conversation_id)
                if title:
                    return title
    return ""


def table_columns(connection, table):
    try:
        return {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('{}')".format(table.replace("'", "''"))
            )
        }
    except sqlite3.Error:
        return set()


def title_from_headers_table(connection, conversation_id):
    columns = table_columns(connection, "composerHeaders")
    id_column = next(
        (name for name in ("composerId", "conversationId", "id") if name in columns),
        "",
    )
    if not id_column:
        return ""

    selected = [
        name for name in ("name", "title", "value", "data", "json") if name in columns
    ]
    if not selected:
        return ""

    quoted_selected = ", ".join('"{}"'.format(name) for name in selected)
    query = 'SELECT {} FROM "composerHeaders" WHERE "{}"=?'.format(
        quoted_selected, id_column
    )

    try:
        row = connection.execute(query, (conversation_id,)).fetchone()
    except sqlite3.Error:
        return ""
    if not row:
        return ""

    for column, value in zip(selected, row):
        if column in ("name", "title"):
            title = clean_label(value)
        else:
            title = title_from_record(parse_json(value), conversation_id)
        if title:
            return title
    return ""


def title_from_key_value_tables(connection, conversation_id):
    exact_keys = (
        "composerData:{}".format(conversation_id),
        "composer:{}".format(conversation_id),
        conversation_id,
    )
    aggregate_keys = ("composer.composerHeaders", "composerHeaders")

    for table in ("cursorDiskKV", "ItemTable"):
        columns = table_columns(connection, table)
        if not {"key", "value"}.issubset(columns):
            continue
        safe_table = '"{}"'.format(table)
        for key in exact_keys + aggregate_keys:
            try:
                row = connection.execute(
                    "SELECT value FROM {} WHERE key=?".format(safe_table), (key,)
                ).fetchone()
            except sqlite3.Error:
                break
            if not row:
                continue
            title = title_from_record(parse_json(row[0]), conversation_id)
            if title:
                return title
    return ""


def title_from_cloud_agents(connection, conversation_id):
    """Cloud agent chats are not composerHeaders rows; names live on ItemTable."""
    for table in ("ItemTable", "cursorDiskKV"):
        columns = table_columns(connection, table)
        if not {"key", "value"}.issubset(columns):
            continue
        try:
            rows = connection.execute(
                'SELECT value FROM "{}" WHERE key LIKE ?'.format(table),
                ("cloudAgentRepository.agents.%",),
            ).fetchall()
        except sqlite3.Error:
            continue
        for (value,) in rows:
            payload = parse_json(value)
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                agent_id = clean_label(item.get("bcId") or item.get("id"))
                if agent_id != conversation_id:
                    continue
                title = clean_label(item.get("name") or item.get("title"))
                if title:
                    return title
    return ""


def cursor_chat_title(conversation_id):
    if not conversation_id or not STATE_DB.is_file():
        return ""

    database_uri = "file:{}?mode=ro".format(quote(str(STATE_DB), safe=""))
    try:
        connection = sqlite3.connect(database_uri, uri=True, timeout=0.5)
    except sqlite3.Error:
        return ""
    try:
        connection.execute("PRAGMA query_only=ON")
        return (
            title_from_headers_table(connection, conversation_id)
            or title_from_key_value_tables(connection, conversation_id)
            or title_from_cloud_agents(connection, conversation_id)
        )
    finally:
        connection.close()


def truncate(value, length):
    if len(value) <= length:
        return value
    shortened = value[:length].rsplit(" ", 1)[0]
    return shortened or value[:length]


def title_parts(workspace, chat_title):
    workspace = clean_label(workspace)
    chat_title = clean_label(chat_title)
    if not workspace or not chat_title:
        return ()

    workspace = truncate(workspace, MAX_WORKSPACE_CHARS)
    available = MAX_TITLE_CHARS - len(workspace) - len(PLAIN_SEPARATOR)
    if available < 1:
        return ()
    return workspace, truncate(chat_title, available)


def peon_match_title(value):
    """Reproduce peon-ping's project-label sanitizer so notify.sh can match $2."""
    return PEON_TITLE_CHARS.sub("", value.strip())[:MAX_TITLE_CHARS]


def store_banner_title(conversation_id, plain_title, banner_title):
    """Cache match key, emoji banner, and ">" fallback for notify.sh."""
    path = cache_path("banner-title", conversation_id)
    if not path:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        prune_stale_entries()
        with open(path, "w") as handle:
            handle.write(
                "{}\n{}\n{}\n".format(
                    peon_match_title(plain_title), banner_title, plain_title
                )
            )
    except OSError:
        pass


def clear_banner_title(conversation_id):
    path = cache_path("banner-title", conversation_id)
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def workspace_label(cwd):
    """Name the folder holding the chat, or 'Home' when there is no project.

    Cursor reports an empty cwd for a window opened without a folder, and peon.sh
    answers that with a hardcoded 'claude'; naming it keeps the banner readable.
    """
    if not cwd:
        return HOME_WORKSPACE_LABEL
    path = os.path.normpath(cwd)
    if path == os.path.normpath(os.path.expanduser("~")):
        return HOME_WORKSPACE_LABEL
    return os.path.basename(path)


def main():
    conversation_id = clean_label(os.environ.get("PEON_SESSION_ID"))
    cwd = clean_label(os.environ.get("PEON_CWD"))
    workspace = workspace_label(cwd)
    parts = title_parts(workspace, cursor_chat_title(conversation_id))
    if not parts:
        clear_banner_title(conversation_id)
        return 1

    plain_title = PLAIN_SEPARATOR.join(parts)
    store_banner_title(conversation_id, plain_title, BANNER_FORMAT.format(*parts))
    print(plain_title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
