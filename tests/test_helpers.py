import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location("monitor_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


balance, openai, setup = (load(name) for name in ("balance", "openai", "setup"))


class HelpersTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        env = patch.dict(os.environ, {"HOME": str(self.home), "XDG_DATA_HOME": str(self.home / "data"), "DEEPSEEK_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)

    def auth(self, data):
        target = self.home / "data/opencode/auth.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data))

    def test_missing_credentials(self):
        self.assertTrue(balance.fetch()["needs_setup"])
        self.assertTrue(openai.fetch()["needs_setup"])

    def test_secure_key_save_and_replace(self):
        for key in ("test-only-first", "test-only-second"):
            self.assertEqual(setup.save_key(key), {"saved": True})
            path = self.home / ".config/omarchy/agents/deepseek.key"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(balance.credential(), key)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_invalid_key(self):
        for key in ("", "two words", "a\nb", "a" * 4097):
            self.assertIn("error", setup.save_key(key))

    def test_credential_priority_and_xdg(self):
        self.auth({"deepseek": {"key": "test-only-opencode"}})
        self.assertEqual(balance.credential(), "test-only-opencode")
        setup.save_key("test-only-file")
        self.assertEqual(balance.credential(), "test-only-file")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only-env"}):
            self.assertEqual(balance.credential(), "test-only-env")

    def test_deepseek_response(self):
        payload = {"is_available": True, "balance_infos": [{"currency": "USD", "total_balance": "2.50"}]}
        with patch.object(balance, "credential", return_value="test-only-key"), patch.object(balance, "urlopen", return_value=io.StringIO(json.dumps(payload))):
            result = balance.fetch()
        self.assertTrue(result["available"])
        self.assertEqual(result["balances"][0]["total"], "2.50")
        self.assertNotIn("test-only-key", json.dumps(result))

    def test_openai_api_key_is_not_oauth(self):
        self.auth({"openai": {"type": "api", "key": "test-only-key"}})
        self.assertTrue(openai.fetch()["needs_setup"])

    def test_malformed_auth(self):
        self.auth([])
        self.assertTrue(balance.fetch()["needs_setup"])
        self.assertIn("error", openai.fetch())

    def test_openai_windows_and_clamping(self):
        result = openai.normalize({"plan_type": "plus", "rate_limit": {
            "primary_window": {"used_percent": -5, "limit_window_seconds": 18000},
            "secondary_window": {"used_percent": 120, "limit_window_seconds": 604800}}})
        self.assertEqual(result["plan"], "plus")
        self.assertEqual([w["used"] for w in result["limits"]], [0, 100])
        self.assertEqual([w["label"] for w in result["limits"]], ["5-hour limit", "Weekly limit"])

    def test_non_finite_usage(self):
        with self.assertRaises(ValueError):
            openai.normalize({"rate_limit": {"primary_window": {"used_percent": float("nan")}}})

    def test_sanitized_network_errors(self):
        self.auth({"openai": {"type": "oauth", "access": "test-only-secret"}})
        for module in (balance, openai):
            for error in (HTTPError("https://example.invalid", 401, "test-only-secret", {}, None), URLError("test-only-secret")):
                with patch.object(balance, "credential", return_value="test-only-secret"), patch.object(module, "urlopen", side_effect=error):
                    result = module.fetch()
                self.assertIn("error", result)
                self.assertNotIn("test-only-secret", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
