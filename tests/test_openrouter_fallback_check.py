import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "openrouter_fallback_check.py"

MODELS_PAYLOAD = {
    "data": [
        {
            "id": "vendor/high-context:free",
            "context_length": 200000,
            "created": 300,
            "pricing": {"prompt": "0", "completion": "0"},
        },
        {
            "id": "vendor/medium-context:free",
            "context_length": 128000,
            "created": 250,
            "pricing": {"prompt": 0, "completion": 0},
        },
        {
            "id": "vendor/throttled:free",
            "context_length": 256000,
            "created": 200,
            "pricing": {"prompt": 0, "completion": 0},
        },
        {
            "id": "vendor/not-free",
            "context_length": 999999,
            "created": 999,
            "pricing": {"prompt": 0, "completion": 0},
        },
    ]
}


class FakeOpenRouterHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/v1/models":
            self.send_error(404)
            return
        body = json.dumps(MODELS_PAYLOAD).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        model = payload["model"]
        if model == "vendor/throttled:free":
            body = json.dumps({"error": "rate limited"}).encode("utf-8")
            self.send_response(429)
        else:
            body = json.dumps({"id": "ok"}).encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class OpenRouterFallbackCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenRouterHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}/api/v1"
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=2)
        cls.server.server_close()

    def write_tier_file(self, tempdir: Path) -> Path:
        tier_path = tempdir / "openrouter_tiers.json"
        tier_path.write_text(
            json.dumps(
                {
                    "min_context_length": 100000,
                    "min_tier_score": 4,
                    "tiers": {
                        "vendor/medium-context:free": {"score": 9, "note": "preferred"},
                        "vendor/high-context:free": {"score": 8, "note": "second"},
                        "vendor/throttled:free": {"score": 4, "note": "allowed but throttled"},
                    },
                }
            ),
            encoding="utf-8",
        )
        return tier_path

    def run_script(self, tempdir: Path):
        tier_path = self.write_tier_file(tempdir)
        env = os.environ.copy()
        env.update(
            {
                "OPENROUTER_API_KEY": "dummy-key",
                "OPENROUTER_BASE_URL": self.base_url,
                "OPENROUTER_FALLBACK_CHAIN_LENGTH": "3",
                "HERMES_CONFIG_PATH": str(tempdir / "config.yaml"),
                "HERMES_STATE_PATH": str(tempdir / "state.json"),
                "HERMES_BACKUP_PATH": str(tempdir / "config.yaml.bak"),
                "HERMES_HOME": str(tempdir / ".hermes"),
                "HERMES_TIER_CONFIG_PATH": str(tier_path),
            }
        )
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_updates_only_fallback_providers_and_preserves_primary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tempdir = Path(tmp)
            original = {
                "model": {
                    "provider": "openai-codex",
                    "default": "gpt-5.4",
                    "base_url": "https://chatgpt.com/backend-api/codex",
                },
                "fallback_providers": [],
                "terminal": {"backend": "local"},
            }
            (tempdir / "config.yaml").write_text(yaml.safe_dump(original, sort_keys=False), encoding="utf-8")

            first = self.run_script(tempdir)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertIn("eligible=3", first.stdout)
            self.assertIn("min_score=4", first.stdout)

            updated = yaml.safe_load((tempdir / "config.yaml").read_text(encoding="utf-8"))
            self.assertEqual(updated["model"], original["model"])
            self.assertEqual(
                updated["fallback_providers"],
                [
                    {"provider": "openrouter", "model": "vendor/medium-context:free"},
                    {"provider": "openrouter", "model": "vendor/high-context:free"},
                    {"provider": "openrouter", "model": "vendor/throttled:free"},
                ],
            )
            self.assertTrue((tempdir / "config.yaml.bak").exists())
            state = json.loads((tempdir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(len(state["fallbacks"]), 3)
            self.assertEqual(state["min_tier_score"], 4)
            self.assertEqual(state["min_context_length"], 100000)
            self.assertTrue(str(tempdir / "openrouter_tiers.json") in state["tier_config_path"])

            second = self.run_script(tempdir)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertIn("no change", second.stdout)


if __name__ == "__main__":
    unittest.main()
