#!/usr/bin/env python3
"""Build a PeonPing title from read-only Cursor or Codex chat metadata.

PeonPing supplies PEON_IDE, PEON_SESSION_ID, and PEON_CWD. This script prints
``agent > workspace > chat-title`` and caches the emoji form for the notify
wrapper.
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
MAX_AGENT_CHARS = 10
MAX_WORKSPACE_CHARS = 20
HOME_WORKSPACE_LABEL = "Home"
RECENTS_WORKSPACE_LABEL = "Recents"
PLAIN_SEPARATOR = " > "
BANNER_FORMAT = "\U0001f4bb {} \U0001f4c2 {} \U0001f4ac {}"
PEON_TITLE_CHARS = re.compile(r"[^A-Za-z0-9 ._-]")


def cursor_state_db():
    return Path(
        os.environ.get(
            "CURSOR_STATE_DB",
            "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
        )
    ).expanduser()


def codex_session_index():
    default = os.path.join(
        os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex")),
        "session_index.jsonl",
    )
    return Path(os.environ.get("CODEX_SESSION_INDEX", default)).expanduser()


def codex_state_db():
    default = os.path.join(
        os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex")),
        "state_5.sqlite",
    )
    return Path(os.environ.get("CODEX_STATE_DB", default)).expanduser()


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
        record.get("composerId") or record.get("conversationId") or record.get("id")
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
    state_db = cursor_state_db()
    if not conversation_id or not state_db.is_file():
        return ""
    database_uri = "file:{}?mode=ro".format(quote(str(state_db), safe=""))
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


def codex_chat_title(session_id):
    """Read the newest matching name from Codex's best-effort session index."""
    conversation_id = clean_label(session_id)
    if conversation_id.startswith("codex-"):
        conversation_id = conversation_id[len("codex-") :]
    index_path = codex_session_index()
    if not conversation_id or not index_path.is_file():
        return ""
    title = ""
    try:
        with index_path.open(errors="replace") as handle:
            for line in handle:
                record = parse_json(line)
                if not isinstance(record, dict):
                    continue
                if clean_label(record.get("id")) != conversation_id:
                    continue
                candidate = clean_label(
                    record.get("thread_name") or record.get("title") or record.get("name")
                )
                if candidate:
                    title = candidate
    except OSError:
        return ""
    return title


def truncate(value, length):
    if len(value) <= length:
        return value
    shortened = value[:length].rsplit(" ", 1)[0]
    return shortened or value[:length]


def title_parts(agent, workspace, chat_title):
    agent = clean_label(agent)
    workspace = clean_label(workspace)
    chat_title = clean_label(chat_title)
    if not agent or not workspace or not chat_title:
        return ()
    agent = truncate(agent, MAX_AGENT_CHARS)
    workspace = truncate(workspace, MAX_WORKSPACE_CHARS)
    available = MAX_TITLE_CHARS - len(agent) - len(workspace) - 2 * len(PLAIN_SEPARATOR)
    if available < 1:
        return ()
    return agent, workspace, truncate(chat_title, available)


def peon_match_title(value):
    return PEON_TITLE_CHARS.sub("", value.strip())[:MAX_TITLE_CHARS]


def store_banner_title(session_id, plain_title, banner_title):
    path = cache_path("banner-title", session_id)
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


def clear_banner_title(session_id):
    path = cache_path("banner-title", session_id)
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def workspace_label(cwd):
    if not cwd:
        return HOME_WORKSPACE_LABEL
    path = os.path.normpath(cwd)
    if path == os.path.normpath(os.path.expanduser("~")):
        return HOME_WORKSPACE_LABEL
    return os.path.basename(path)


def codex_originator(transcript_path):
    path = Path(str(transcript_path or "")).expanduser()
    if not path.is_file():
        return ""
    try:
        with path.open(errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= 32:
                    break
                record = parse_json(line)
                if not isinstance(record, dict) or record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                if isinstance(payload, dict):
                    return clean_label(payload.get("originator"))
    except OSError:
        pass
    return ""


def codex_project_context(session_id):
    conversation_id = clean_label(session_id)
    if conversation_id.startswith("codex-"):
        conversation_id = conversation_id[len("codex-") :]
    state_db = codex_state_db()
    if not conversation_id or not state_db.is_file():
        return None
    database_uri = "file:{}?mode=ro".format(quote(str(state_db), safe=""))
    try:
        connection = sqlite3.connect(database_uri, uri=True, timeout=0.5)
    except sqlite3.Error:
        return None
    try:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute(
            """
            SELECT threads.project_id, projects.name
            FROM threads
            LEFT JOIN projects ON projects.id = threads.project_id
            WHERE threads.id = ?
            """,
            (conversation_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    if not row:
        return None
    return clean_label(row[0]), clean_label(row[1])


def codex_workspace_label(cwd, session_id, transcript_path):
    fallback = workspace_label(cwd)
    if codex_originator(transcript_path).lower() != "codex desktop":
        return fallback
    project_context = codex_project_context(session_id)
    if project_context is None:
        return fallback
    project_id, project_name = project_context
    if not project_id:
        return RECENTS_WORKSPACE_LABEL
    return project_name or fallback


def agent_label(ide, session_id):
    if clean_label(ide).lower() == "codex" or session_id.startswith("codex-"):
        return "Codex"
    return "Cursor"


def chat_title(ide, session_id):
    if clean_label(ide).lower() == "codex" or session_id.startswith("codex-"):
        return codex_chat_title(session_id)
    return cursor_chat_title(session_id)


def main():
    session_id = clean_label(os.environ.get("PEON_SESSION_ID"))
    cwd = clean_label(os.environ.get("PEON_CWD"))
    ide = clean_label(os.environ.get("PEON_IDE"))
    transcript_path = clean_label(os.environ.get("PEON_TRANSCRIPT_PATH"))
    agent = agent_label(ide, session_id)
    workspace = (
        codex_workspace_label(cwd, session_id, transcript_path)
        if agent == "Codex"
        else workspace_label(cwd)
    )
    parts = title_parts(agent, workspace, chat_title(ide, session_id))
    if not parts:
        clear_banner_title(session_id)
        return 1
    plain_title = PLAIN_SEPARATOR.join(parts)
    store_banner_title(session_id, plain_title, BANNER_FORMAT.format(*parts))
    print(plain_title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
