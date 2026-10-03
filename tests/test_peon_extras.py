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
import install_opencode_plugin
import opencode_hook
import notification_title


class NotificationTitleTests(unittest.TestCase):
    def test_opencode_title_uses_session_title_from_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_file = Path(directory, "banner-title-sesabc")
            stdout = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {
                        "PEON_IDE": "opencode",
                        "PEON_SESSION_ID": "ses_abc",
                        "PEON_CWD": "/work/peon-extras",
                        "PEON_CHAT_TITLE": "Review the new adapter",
                    },
                ),
                patch.object(notification_title, "CACHE_DIR", directory),
                patch.object(
                    notification_title,
                    "cache_path",
                    return_value=str(cache_file),
                ),
                patch.object(notification_title, "prune_stale_entries"),
                redirect_stdout(stdout),
            ):
                result = notification_title.main()

            self.assertEqual(result, 0)
            self.assertEqual(
                stdout.getvalue(),
                "OpenCode > peon-extras > Review the new adapter\n",
            )

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
    def test_permission_request_uses_latest_reviewer_across_transcript_formats(self):
        def context(reviewer):
            return {"type": "turn_context", "payload": {"approvals_reviewer": reviewer}}

        def settings(reviewer):
            return {
                "type": "event_msg",
                "payload": {
                    "type": "thread_settings_applied",
                    "thread_settings": {"approvals_reviewer": reviewer},
                },
            }

        cases = [
            ([context("auto_review")], 0),
            ([context("guardian_subagent")], 0),
            ([context("user")], 1),
            ([settings("user"), context("auto_review")], 0),
            ([settings("auto_review"), context("user")], 1),
            ([context("auto_review"), settings("user")], 1),
            ([context("user"), settings("auto_review")], 0),
            ([context("auto_review"), {"type": "turn_context", "payload": {}}], 1),
        ]
        for records, expected_notifications in cases:
            with self.subTest(records=records), tempfile.TemporaryDirectory() as directory:
                transcript = Path(directory, "rollout.jsonl")
                transcript.write_text("".join(json.dumps(item) + "\n" for item in records))
                event = {
                    "hook_event_name": "PermissionRequest",
                    "tool_name": "exec_command",
                    "transcript_path": str(transcript),
                }
                with (
                    patch.object(sys, "stdin", io.StringIO(json.dumps(event))),
                    patch.object(codex_hook, "run_adapter", return_value=0) as adapter,
                ):
                    self.assertEqual(codex_hook.main(), 0)
                self.assertEqual(adapter.call_count, expected_notifications)

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


class OpenCodePluginInstallerTests(unittest.TestCase):
    def test_merge_preserves_existing_plugins_and_is_idempotent(self):
        original = {
            "$schema": "https://opencode.ai/config.json",
            "plugins": ["-opencode.provider.vllm", "existing-plugin"],
            "mcp": {"servers": {"docs": {"type": "remote"}}},
        }

        merged = install_opencode_plugin.merge(original, "/runtime/opencode")

        self.assertEqual(
            merged,
            {
                "$schema": "https://opencode.ai/config.json",
                "plugins": [
                    "-opencode.provider.vllm",
                    "existing-plugin",
                    "/runtime/opencode",
                ],
                "mcp": {"servers": {"docs": {"type": "remote"}}},
            },
        )
        self.assertEqual(
            install_opencode_plugin.merge(merged, "/runtime/opencode"), merged
        )

    def test_compaction_events_keep_banners_without_running_peon(self):
        banners = []
        peon_events = []
        before = {
            "hook_event_name": "PreCompact",
            "session_id": "ses_abc",
            "cwd": "/work/repo",
            "title": "Review",
            "context_tokens": 90_000,
            "context_window_size": 100_000,
        }
        after = {
            **before,
            "hook_event_name": "PostCompact",
            "context_tokens": 12_000,
        }
        send_banner = lambda payload, message: banners.append(
            (payload["hook_event_name"], payload["source"], message)
        )
        run_peon = lambda payload: peon_events.append(payload) or 0

        before_result = opencode_hook.handle_event(
            before, peon_runner=run_peon, banner_sender=send_banner
        )
        after_result = opencode_hook.handle_event(
            after, peon_runner=run_peon, banner_sender=send_banner
        )

        self.assertEqual((before_result, after_result), (0, 0))
        self.assertEqual(
            banners,
            [
                (
                    "PreCompact",
                    "opencode",
                    "Summarizing: 90K / 100K Tokens (90% Full)",
                ),
                (
                    "PostCompact",
                    "opencode",
                    "Done summarizing: 12K / 100K Tokens (12% Full)",
                ),
            ],
        )
        self.assertEqual(peon_events, [])

    def test_post_compact_banner_uses_standard_usage_wording_for_summary_output(self):
        banners = []
        result = opencode_hook.handle_event(
            {
                "hook_event_name": "PostCompact",
                "context_tokens": 96,
                "context_window_size": 175_000,
            },
            banner_sender=lambda _payload, message: banners.append(message),
        )

        self.assertEqual(result, 0)
        self.assertEqual(
            banners,
            ["Done summarizing: 96 / 175K Tokens (0% Full)"],
        )

    def test_compaction_banner_color_tracks_before_and_after_stage(self):
        with (
            patch.object(opencode_hook, "prime_title", return_value="Review"),
            patch.object(opencode_hook.os.path, "isfile", return_value=True),
            patch.object(opencode_hook.subprocess, "run") as run,
        ):
            opencode_hook.handle_event(
                {"hook_event_name": "PreCompact", "session_id": "ses_before"}
            )
            opencode_hook.handle_event(
                {"hook_event_name": "PostCompact", "session_id": "ses_after"}
            )

        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual([command[-1] for command in commands], ["red", "blue"])

    def test_trace_records_only_sanitized_peon_event_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory, "trace-enabled")
            marker.touch()
            trace_log = Path(directory, "trace.jsonl")
            with (
                patch.object(opencode_hook, "TRACE_MARKER_PATH", marker),
                patch.object(opencode_hook, "TRACE_LOG_PATH", trace_log),
            ):
                result = opencode_hook.handle_event(
                    {
                        "hook_event_name": "Stop",
                        "session_id": "ses_sensitive",
                        "cwd": "/work/repo",
                        "title": "Review",
                        "message": "this message must not be traced",
                    },
                    peon_runner=lambda _event: 0,
                )

            trace_line = trace_log.read_text()

        record = json.loads(trace_line.split(opencode_hook.TRACE_PREFIX, 1)[1])
        self.assertEqual(result, 0)
        self.assertEqual(
            record,
            {
                "phase": "peon",
                "type": "Stop",
                "hasTitle": True,
                "hasWorkspace": True,
            },
        )
        self.assertNotIn("this message must not be traced", trace_line)


if __name__ == "__main__":
    unittest.main()
