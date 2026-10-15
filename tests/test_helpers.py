import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
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
        api = patch.object(openai.subprocess, "run", side_effect=FileNotFoundError)
        api.start()
        self.addCleanup(api.stop)

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
        self.assertTrue(openai.fetch()["needs_setup"])

    def api_credentials(self, entries):
        return patch.object(openai.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps({"data": entries})))

    def test_v2_browser_login_over_stale_legacy_and_token_sharing(self):
        self.auth({"openai": {"type": "oauth", "access": "test-only-stale", "expires": 1}})
        entries = [
            {"integrationID": "openai", "active": True, "value": {
                "type": "oauth", "methodID": "chatgpt-token-sharing", "access": "test-only-sharing"}},
            {"integrationID": "openai", "active": False, "value": {
                "type": "oauth", "methodID": "chatgpt-browser", "access": "test-only-browser",
                "metadata": {"accountID": "test-only-account"}}},
        ]
        payload = {"rate_limit": {"primary_window": {"used_percent": 20}}}
        with self.api_credentials(entries), patch.object(openai, "urlopen", return_value=io.StringIO(json.dumps(payload))) as request:
            result = openai.fetch()
        self.assertEqual(result["limits"][0]["used"], 20)
        headers = dict(request.call_args.args[0].header_items())
        self.assertEqual(headers["Authorization"], "Bearer test-only-browser")
        self.assertEqual(headers["Chatgpt-account-id"], "test-only-account")

    def test_v2_empty_store_does_not_revive_legacy_login(self):
        self.auth({"openai": {"type": "oauth", "access": "test-only-stale"}})
        with self.api_credentials([]), patch.object(openai, "urlopen") as request:
            self.assertTrue(openai.fetch()["needs_setup"])
        request.assert_not_called()

    def test_token_sharing_is_not_reported_as_expired(self):
        entries = [{"integrationID": "openai", "active": True, "value": {
            "type": "oauth", "methodID": "chatgpt-token-sharing", "access": "test-only-sharing"}}]
        with self.api_credentials(entries), patch.object(openai, "urlopen") as request:
            result = openai.fetch()
        self.assertIn("token-sharing", result["error"])
        self.assertNotIn("expired", result["error"])
        request.assert_not_called()

    def test_rejected_browser_tries_another_saved_browser(self):
        entries = [{"integrationID": "openai", "active": active, "value": {
            "type": "oauth", "methodID": "chatgpt-browser", "access": key}}
            for active, key in ((False, "test-only-other"), (True, "test-only-active"))]
        payload = {"rate_limit": {"primary_window": {"used_percent": 10}}}
        rejected = HTTPError("https://example.invalid", 401, "secret-error", {}, None)
        with self.api_credentials(entries), patch.object(openai, "urlopen", side_effect=[rejected, io.StringIO(json.dumps(payload))]) as request:
            self.assertIn("limits", openai.fetch())
        self.assertEqual(request.call_args_list[0].args[0].get_header("Authorization"), "Bearer test-only-active")
        self.assertEqual(request.call_count, 2)

    def test_expired_browser_does_not_make_request(self):
        self.auth({"openai": {"type": "oauth", "access": "test-only-stale", "expires": 1}})
        with patch.object(openai, "urlopen") as request:
            self.assertIn("expired", openai.fetch()["error"])
        request.assert_not_called()

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
