import json
import http.server
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
OPENCODE = shutil.which("opencode")


class FakeOpenAIHandler(http.server.BaseHTTPRequestHandler):
    requested = threading.Event()

    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.requested.set()
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        chunks = [
            {
                "id": "chatcmpl-peon-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fake-test",
                "choices": [
                    {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
                ],
            },
            {
                "id": "chatcmpl-peon-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fake-test",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "Lifecycle check passed."},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chatcmpl-peon-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fake-test",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
        ]
        payload = "".join(
            "data: {}\n\n".format(json.dumps(chunk)) for chunk in chunks
        ) + "data: [DONE]\n\n"
        body = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@unittest.skipUnless(OPENCODE, "OpenCode is not installed")
class OpenCodePluginLoadTests(unittest.TestCase):
    def test_root_session_lifecycle_reaches_the_fake_peon_runtime(self):
        version = subprocess.run(
            [OPENCODE, "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        if not version.startswith("opencode v2."):
            self.skipTest("the installed OpenCode binary is not V2")

        with tempfile.TemporaryDirectory(prefix="peon-opencode-") as temporary:
            FakeOpenAIHandler.requested.clear()
            root = Path(temporary)
            home = root / "home"
            config_dir = root / "config"
            workspace = root / "workspace"
            fake_peon = root / "fake-peon"
            for directory in (home, config_dir / "opencode", workspace, fake_peon):
                directory.mkdir(parents=True, exist_ok=True)

            capture_path = root / "captured-events.jsonl"
            (fake_peon / "peon.sh").write_text(
                'cat >> "$PEON_CAPTURE"\nprintf \'\\n\' >> "$PEON_CAPTURE"\n'
            )
            fake_peon_server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), FakeOpenAIHandler
            )
            model_thread = threading.Thread(
                target=fake_peon_server.serve_forever, daemon=True
            )
            model_thread.start()
            (config_dir / "opencode" / "opencode.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://opencode.ai/config.json",
                        "model": "fake/test",
                        "plugins": [str(REPO / "opencode")],
                        "providers": {
                            "fake": {
                                "name": "Fake OpenAI",
                                "env": ["FAKE_API_KEY"],
                                "package": "@opencode/ai/providers/openai-compatible",
                                "settings": {
                                    "baseURL": "http://127.0.0.1:{}/v1".format(
                                        fake_peon_server.server_port
                                    ),
                                },
                                "models": {
                                    "test": {
                                        "name": "Fake model",
                                        "limit": {"context": 100_000, "output": 4096},
                                    }
                                },
                            }
                        },
                    }
                )
            )

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]

            password = "peon-opencode-test-only"
            environment = os.environ.copy()
            environment.update(
                {
                    "HOME": str(home),
                    "XDG_CONFIG_HOME": str(config_dir),
                    "OPENCODE_SERVER_PASSWORD": password,
                    "PEON_DIR": str(fake_peon),
                    "PEON_CAPTURE": str(capture_path),
                    "FAKE_API_KEY": "test-only",
                }
            )
            log_path = root / "server.log"
            with log_path.open("w") as server_log:
                server = subprocess.Popen(
                    [
                        OPENCODE,
                        "--log-level",
                        "debug",
                        "serve",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=workspace,
                    env=environment,
                    stdout=server_log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    base_url = "http://127.0.0.1:{}".format(port)
                    client_environment = environment.copy()
                    client_environment["OPENCODE_PASSWORD"] = password

                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        if server.poll() is not None:
                            self.fail("OpenCode server exited during startup")
                        try:
                            subprocess.run(
                                [
                                    OPENCODE,
                                    "api",
                                    "--server",
                                    base_url,
                                    "get",
                                    "/api/info",
                                ],
                                cwd=workspace,
                                env=client_environment,
                                capture_output=True,
                                text=True,
                                timeout=2,
                                check=True,
                            )
                            break
                        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                            time.sleep(0.1)
                    else:
                        self.fail("OpenCode API did not become ready")

                    plugin_diagnostics = "plugin list was not queried"
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        plugin_result = subprocess.run(
                            [
                                OPENCODE,
                                "api",
                                "--server",
                                base_url,
                                "get",
                                "/api/plugin",
                            ],
                            cwd=workspace,
                            env=client_environment,
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                        plugin_diagnostics = plugin_result.stdout or plugin_result.stderr
                        if plugin_result.returncode == 0:
                            try:
                                active_plugins = json.loads(plugin_result.stdout).get("data", [])
                            except (json.JSONDecodeError, AttributeError):
                                active_plugins = []
                            if any(
                                plugin.get("id") == "peon-extras.opencode"
                                for plugin in active_plugins
                            ):
                                break
                        time.sleep(0.1)
                    else:
                        self.fail(
                            "OpenCode did not activate the local plugin; plugin list:\n{}".format(
                                plugin_diagnostics
                            )
                        )

                    created = subprocess.run(
                        [
                            OPENCODE,
                            "api",
                            "--server",
                            base_url,
                            "post",
                            "/api/session",
                            "--data",
                            json.dumps({"title": "Plugin load verification"}),
                        ],
                        cwd=workspace,
                        env=client_environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True,
                    )
                    response = json.loads(created.stdout)
                    session = response.get("data", response)
                    session_id = session["id"]

                    deadline = time.monotonic() + 5
                    events = []
                    while time.monotonic() < deadline:
                        if capture_path.exists():
                            events = [
                                json.loads(line)
                                for line in capture_path.read_text().splitlines()
                            ]
                            if any(
                                event["hook_event_name"] == "SessionStart"
                                for event in events
                            ):
                                break
                        time.sleep(0.05)
                    self.assertTrue(
                        any(event["hook_event_name"] == "SessionStart" for event in events),
                        "SessionStart did not reach the fake Peon runtime",
                    )

                    subprocess.run(
                        [
                            OPENCODE,
                            "api",
                            "--server",
                            base_url,
                            "post",
                            "/api/session/{}/prompt".format(session_id),
                            "--data",
                            json.dumps(
                                {
                                    "text": "Reply with one sentence and do not use tools."
                                }
                            ),
                        ],
                        cwd=workspace,
                        env=client_environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True,
                    )
                    self.assertTrue(
                        FakeOpenAIHandler.requested.wait(timeout=15),
                        "OpenCode did not dispatch the prompt to the local fake model",
                    )
                    subprocess.run(
                        [
                            OPENCODE,
                            "api",
                            "--server",
                            base_url,
                            "post",
                            "/api/experimental/session/{}/wait".format(session_id),
                            "--data",
                            "{}",
                        ],
                        cwd=workspace,
                        env=client_environment,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=True,
                    )

                    deadline = time.monotonic() + 5
                    events = []
                    while time.monotonic() < deadline:
                        if capture_path.exists():
                            try:
                                events = [
                                    json.loads(line)
                                    for line in capture_path.read_text().splitlines()
                                ]
                                names = [event["hook_event_name"] for event in events]
                                if "Stop" in names:
                                    break
                            except (OSError, json.JSONDecodeError):
                                pass
                        time.sleep(0.05)
                    diagnostics = log_path.read_text()
                    self.assertTrue(
                        "Stop" in [event["hook_event_name"] for event in events],
                        "V2 execution lifecycle did not reach the fake Peon runtime; "
                        "captured events: {}\nserver log:\n{}".format(events, diagnostics),
                    )
                    by_name = {event["hook_event_name"]: event for event in events}
                    self.assertEqual(
                        [event["hook_event_name"] for event in events],
                        ["SessionStart", "UserPromptSubmit", "Stop"],
                    )
                    self.assertEqual(by_name["SessionStart"]["title"], "Plugin load verification")
                    self.assertEqual(by_name["UserPromptSubmit"]["session_id"], session_id)
                    self.assertEqual(by_name["Stop"]["session_id"], session_id)
                    self.assertEqual(by_name["Stop"]["title"], "Plugin load verification")
                    self.assertEqual(by_name["Stop"]["cwd"], str(workspace.resolve()))
                    self.assertEqual(by_name["Stop"]["message"], "Lifecycle check passed.")
                    self.assertEqual(by_name["Stop"]["source"], "opencode")
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
                    fake_peon_server.shutdown()
                    fake_peon_server.server_close()


if __name__ == "__main__":
    unittest.main()
