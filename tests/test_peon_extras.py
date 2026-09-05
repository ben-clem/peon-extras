import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import codex_hook
import install_codex_hooks
import notification_title


class NotificationTitleTests(unittest.TestCase):
    def make_codex_state(self, path, project_id=None, project_name=None, source="vscode"):
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                project_id TEXT
            );
            """
        )
        if project_id:
            connection.execute(
                "INSERT INTO projects (id, name) VALUES (?, ?)",
                (project_id, project_name),
            )
        connection.execute(
            "INSERT INTO threads (id, source, project_id) VALUES (?, ?, ?)",
            ("abc", source, project_id),
        )
        connection.commit()
        connection.close()

    def test_codex_title_uses_latest_matching_index_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory, "session_index.jsonl")
            records = [
                {"id": "abc", "thread_name": "Old title"},
                {"id": "other", "thread_name": "Ignore me"},
                {"id": "abc", "thread_name": "Current conversation"},
            ]
            index.write_text("".join(json.dumps(item) + "\n" for item in records))
            with patch.dict(os.environ, {"CODEX_SESSION_INDEX": str(index)}):
                self.assertEqual(
                    notification_title.codex_chat_title("codex-abc"),
                    "Current conversation",
                )

    def test_shared_title_format_stays_within_peon_limit(self):
        parts = notification_title.title_parts(
            "Cursor",
            "a-very-long-workspace-folder",
            "A long conversation title with details",
        )
        rendered = notification_title.PLAIN_SEPARATOR.join(parts)
        self.assertLessEqual(len(rendered), notification_title.MAX_TITLE_CHARS)
        self.assertTrue(rendered.startswith("Cursor > a-very-long-workspac > "))

    def test_codex_desktop_projectless_workspace_is_recents(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory, "state.sqlite")
            transcript = Path(directory, "rollout.jsonl")
            self.make_codex_state(state)
            transcript.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"originator": "Codex Desktop"},
                    }
                )
                + "\n"
            )
            with patch.dict(os.environ, {"CODEX_STATE_DB": str(state)}):
                self.assertEqual(
                    notification_title.codex_workspace_label(
                        "/Users/me/Documents/Codex/2026-09-05/wh",
                        "codex-abc",
                        str(transcript),
                    ),
                    "Recents",
                )

    def test_codex_desktop_project_workspace_uses_project_name(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory, "state.sqlite")
            transcript = Path(directory, "rollout.jsonl")
            self.make_codex_state(state, "project-1", "Peon Extras")
            transcript.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"originator": "Codex Desktop"},
                    }
                )
                + "\n"
            )
            with patch.dict(os.environ, {"CODEX_STATE_DB": str(state)}):
                self.assertEqual(
                    notification_title.codex_workspace_label(
                        "/work/peon-extras", "codex-abc", str(transcript)
                    ),
                    "Peon Extras",
                )

    def test_codex_cli_workspace_keeps_directory_name(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory, "state.sqlite")
            transcript = Path(directory, "rollout.jsonl")
            self.make_codex_state(state, source="cli")
            transcript.write_text(
                json.dumps(
                    {"type": "session_meta", "payload": {"originator": "codex_cli_rs"}}
                )
                + "\n"
            )
            with patch.dict(os.environ, {"CODEX_STATE_DB": str(state)}):
                self.assertEqual(
                    notification_title.codex_workspace_label(
                        "/work/peon-extras", "codex-abc", str(transcript)
                    ),
                    "peon-extras",
                )


class CodexHookTests(unittest.TestCase):
    def test_permission_request_stays_silent_when_auto_review_is_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory, "rollout.jsonl")
            transcript.write_text(
                json.dumps(
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "thread_settings_applied",
                            "thread_settings": {
                                "approvals_reviewer": "auto_review"
                            },
                        },
                    }
                )
                + "\n"
            )
            event = {
                "hook_event_name": "PermissionRequest",
                "tool_name": "apply_patch",
                "transcript_path": str(transcript),
            }
            with (
                patch.object(sys, "stdin", io.StringIO(json.dumps(event))),
                patch.object(codex_hook, "run_adapter", return_value=0) as adapter,
            ):
                self.assertEqual(codex_hook.main(), 0)
        adapter.assert_not_called()

    def test_permission_request_reaches_peon_without_auto_review(self):
        event = {
            "hook_event_name": "PermissionRequest",
            "tool_name": "apply_patch",
        }
        with (
            patch.object(sys, "stdin", io.StringIO(json.dumps(event))),
            patch.object(codex_hook, "run_adapter", return_value=0) as adapter,
        ):
            self.assertEqual(codex_hook.main(), 0)
        adapter.assert_called_once()

    def test_request_user_input_becomes_question_notification(self):
        event = {
            "session_id": "abc",
            "cwd": "/work/repo",
            "tool_input": {
                "questions": [
                    {"header": "Choice", "question": "Which route should I take?"}
                ]
            },
        }
        payload = codex_hook.question_payload(event)
        self.assertEqual(payload["hook_event_name"], "Notification")
        self.assertEqual(payload["notification_type"], "elicitation_dialog")
        self.assertEqual(payload["message"], "Which route should I take?")
        self.assertEqual(payload["session_id"], "codex-abc")

    def test_latest_context_usage_reads_tail_token_record(self):
        records = [
            {"type": "event_msg", "payload": {"type": "something_else"}},
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {"total_tokens": 75000},
                        "model_context_window": 100000,
                    },
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory, "rollout.jsonl")
            transcript.write_text(
                "".join(json.dumps(item) + "\n" for item in records)
            )
            self.assertEqual(
                codex_hook.latest_context_usage(str(transcript)),
                (75000, 100000, 75.0),
            )


class CodexHookInstallerTests(unittest.TestCase):
    def test_main_skips_unchanged_hook_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            hooks_path = Path(directory, "hooks.json")
            first_output = io.StringIO()
            with redirect_stdout(first_output):
                self.assertEqual(
                    install_codex_hooks.main(
                        ["install_codex_hooks.py", str(hooks_path), "/runtime"]
                    ),
                    0,
                )
            self.assertTrue(first_output.getvalue().startswith("wrote "))

            second_output = io.StringIO()
            with (
                patch.object(install_codex_hooks, "write_atomic") as write_atomic,
                redirect_stdout(second_output),
            ):
                self.assertEqual(
                    install_codex_hooks.main(
                        ["install_codex_hooks.py", str(hooks_path), "/runtime"]
                    ),
                    0,
                )
            write_atomic.assert_not_called()
            self.assertTrue(second_output.getvalue().startswith("unchanged "))

    def test_merge_preserves_unrelated_rules_and_replaces_peon_rules(self):
        data = {
            "description": "mine",
            "hooks": {
                "Stop": [
                    {"hooks": [{"type": "command", "command": "my-stop"}]},
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash ~/.claude/hooks/peon-ping/adapters/codex.sh",
                            }
                        ]
                    },
                ]
            },
        }
        merged = install_codex_hooks.merge(data, "/runtime")
        stop_rules = merged["hooks"]["Stop"]
        self.assertEqual(stop_rules[0]["hooks"][0]["command"], "my-stop")
        self.assertEqual(
            stop_rules[1]["hooks"][0]["command"],
            'python3 "/runtime/codex_hook.py"',
        )
        self.assertEqual(
            merged["hooks"]["PreToolUse"][-1]["matcher"],
            "^request_user_input$",
        )
        self.assertEqual(
            merged["hooks"]["SessionEnd"][-1]["hooks"][0]["timeout"], 3
        )
        self.assertEqual(merged["description"], "mine")


if __name__ == "__main__":
    unittest.main()
