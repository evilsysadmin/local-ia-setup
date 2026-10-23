import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("local_setup", HERE / "scripts/local_setup.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ConfigTests(unittest.TestCase):
    def cfg(self, **changes):
        options = dict(upstream_model_id="Ternary-Bonsai-2-27B-PQ2_0.gguf", context=32768,
                       output=4096, keep=2048, buffer=4096, base_url="http://127.0.0.1:8080")
        options.update(changes)
        return mod.generate_config(**options)

    def test_open_code_v2_schema_and_local_only(self):
        cfg = self.cfg()
        self.assertEqual(cfg["model"], "bonsai-local/bonsai")
        provider = cfg["providers"]["bonsai-local"]
        self.assertEqual(provider["models"]["bonsai"]["modelID"], "Ternary-Bonsai-2-27B-PQ2_0.gguf")
        self.assertEqual(provider["settings"]["baseURL"], "http://127.0.0.1:8080/v1")
        self.assertEqual(cfg["policies"][0]["effect"], "deny")
        self.assertEqual(cfg["policies"][1]["resource"], "bonsai-local")
        self.assertEqual(cfg["permissions"][3], {"action": "shell", "resource": "git push *", "effect": "deny"})
        self.assertNotIn("anthropic", json.dumps(cfg))
        self.assertNotIn("apiKey", json.dumps(cfg))

    def test_compaction_budget_contract(self):
        cfg = self.cfg(context=16384, output=2048, keep=1024, buffer=2048)
        self.assertEqual(cfg["compaction"]["buffer"], 2048)
        self.assertEqual(cfg["providers"]["bonsai-local"]["models"]["bonsai"]["limit"]["context"], 16384)
        with self.assertRaises(ValueError):
            self.cfg(context=8192, output=4096, keep=2048, buffer=4096)

    def test_reject_remote_endpoint(self):
        for endpoint in ["https://127.0.0.1:8080", "http://0.0.0.0:8080", "http://example.com:8080", "http://127.0.0.1:8080/path", "http://x:secret@localhost:8080"]:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                mod.validate_base_url(endpoint)

    def test_config_backup_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opencode.json"
            path.write_text('{"provider":"claude"}\n')
            status = mod.write_config(self.cfg(), path)
            self.assertEqual(status, "Written")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            backups = list(Path(tmp).glob("opencode.json.bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertIn('claude', backups[0].read_text())
            self.assertEqual(mod.write_config(self.cfg(), path), "Unchanged")
            self.assertEqual(len(list(Path(tmp).glob("opencode.json.bak-*"))), 1)

    def test_model_id_from_local_api(self):
        with patch.object(mod, 'fetch_json', return_value={"data": [{"id": "bonsai-test"}]}):
            self.assertEqual(mod.model_id("http://127.0.0.1:8080"), "bonsai-test")
        with patch.object(mod, 'fetch_json', return_value={"data": []}):
            with self.assertRaises(ValueError):
                mod.model_id("http://127.0.0.1:8080")

    def test_readiness_waits_for_model_load(self):
        ticks = [0.0]
        def clock():
            return ticks[0]
        def sleep(seconds):
            ticks[0] += seconds
        responses = [{"status": "loading model"}, {"status": "ok"}]
        with patch.object(mod, 'fetch_json', side_effect=responses) as health, \
             patch.object(mod, 'model_id', return_value='bonsai-test') as model:
            result = mod.wait_until_ready("http://127.0.0.1:8080", timeout=10,
                                          interval=2, clock=clock, sleeper=sleep)
        self.assertEqual(result, 'bonsai-test')
        self.assertEqual(health.call_count, 2)
        model.assert_called_once()

    def test_readiness_times_out_without_successful_health(self):
        ticks = [0.0]
        def clock():
            return ticks[0]
        def sleep(seconds):
            ticks[0] += seconds
        with patch.object(mod, 'fetch_json', return_value={"status": "loading model"}):
            with self.assertRaisesRegex(RuntimeError, 'not ready after 5s'):
                mod.wait_until_ready("http://127.0.0.1:8080", timeout=5,
                                     interval=2, clock=clock, sleeper=sleep)
        self.assertLessEqual(ticks[0], 5)

    def test_readiness_rejects_invalid_timeout(self):
        with self.assertRaises(ValueError):
            mod.wait_until_ready("http://127.0.0.1:8080", timeout=0)

    def test_context_mismatch_rejected(self):
        with patch.object(mod, 'fetch_json', return_value={"default_generation_settings": {"n_ctx": 8192}}):
            with self.assertRaises(ValueError):
                mod.check_server_context("http://127.0.0.1:8080", 32768)


if __name__ == '__main__':
    unittest.main()
