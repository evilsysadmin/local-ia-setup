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
                       output=4096, keep=2048, buffer=12288, base_url="http://127.0.0.1:8080")
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
        cfg = self.cfg(context=16384, output=2048, keep=1024, buffer=6144)
        self.assertEqual(cfg["compaction"]["buffer"], 6144)
        self.assertEqual(cfg["providers"]["bonsai-local"]["models"]["bonsai"]["limit"]["context"], 16384)
        with self.assertRaises(ValueError):
            self.cfg(context=8192, output=4096, keep=2048, buffer=4096)

    def test_avoid_compaction_summary_truncation(self):
        self.assertEqual(mod.recommended_compaction_buffer(32768, 4096, 2048), 12288)
        self.assertEqual(mod.recommended_compaction_buffer(49152, 4096, 2048), 18432)
        with self.assertRaisesRegex(ValueError, "Compaction buffer 4096 is too small"):
            self.cfg(buffer=4096)
        with self.assertRaisesRegex(ValueError, "cannot safely allocate"):
            mod.recommended_compaction_buffer(8192, 4096, 2048)

    def test_repair_old_global_config_offline_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opencode.json"
            cfg = self.cfg()
            cfg["compaction"]["buffer"] = 4096
            cfg["customPreference"] = {"doNotDelete": True}
            path.write_text(json.dumps(cfg))
            self.assertEqual(mod.fix_compaction(path), "Written")
            changed = json.loads(path.read_text())
            self.assertEqual(changed["compaction"]["buffer"], 12288)
            self.assertEqual(changed["customPreference"], {"doNotDelete": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            backups = list(Path(tmp).glob("opencode.json.bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text())["compaction"]["buffer"], 4096)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(mod.fix_compaction(path), "Unchanged")
            self.assertEqual(len(list(Path(tmp).glob("opencode.json.bak-*"))), 1)

    def test_repair_only_repo_managed_config_and_no_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "external.json"
            p.write_text('{"model":"other/provider"}')
            with self.assertRaisesRegex(ValueError, "not the managed Bonsai"):
                mod.fix_compaction(p)
            link = Path(tmp) / "opencode.json"
            link.symlink_to(p)
            with self.assertRaisesRegex(ValueError, "symlinked"):
                mod.fix_compaction(link)
            self.assertEqual(p.read_text(), '{"model":"other/provider"}')

    def test_repair_preserves_disabled_auto_and_stronger_buffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "opencode.json"
            cfg = self.cfg()
            cfg["compaction"]["auto"] = False
            cfg["compaction"]["buffer"] = 20000
            p.write_text(json.dumps(cfg))
            self.assertEqual(mod.fix_compaction(p), "Unchanged")
            self.assertFalse(json.loads(p.read_text())["compaction"]["auto"])

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


    def test_opencode_cli_version_variants(self):
        accepted = ["opencode v2.1.3", "opencode 2.1.3", "v2.1.3", "2.1.3",
                    "opencode v2.1.3-beta.2"]
        denied = ["opencode v1.9.99", "opencode v12.1.3", "opencode v20.1.3",
                  "not opencode 2.1.3", "opencode version unknown", "", "v2.1",
                  "opencode v2.1.3 ignored"]
        for version in accepted:
            with self.subTest(version=version):
                self.assertTrue(mod.valid_opencode_v2_version(version))
        for version in denied:
            with self.subTest(version=version):
                self.assertFalse(mod.valid_opencode_v2_version(version))

    def test_opencode_v2_installed_checks_exit_code_and_fails_safely(self):
        from subprocess import CompletedProcess, TimeoutExpired
        with patch.object(mod.shutil, "which", return_value="/usr/bin/opencode"), \
             patch.object(mod.subprocess, "run", return_value=CompletedProcess(
                 ["opencode", "--version"], 0, "opencode v2.1.3\n", "")):
            self.assertTrue(mod.opencode_v2_installed())
        with patch.object(mod.shutil, "which", return_value="/usr/bin/opencode"), \
             patch.object(mod.subprocess, "run", return_value=CompletedProcess(
                 ["opencode", "--version"], 1, "opencode v2.1.3\n", "")):
            self.assertFalse(mod.opencode_v2_installed())
        with patch.object(mod.shutil, "which", return_value="/usr/bin/opencode"), \
             patch.object(mod.subprocess, "run", side_effect=TimeoutExpired("opencode", 10)):
            self.assertFalse(mod.opencode_v2_installed())
        with patch.object(mod.shutil, "which", return_value=None):
            self.assertFalse(mod.opencode_v2_installed())

    def test_cli_shared_version_gate(self):
        with patch.object(mod, "opencode_v2_installed", return_value=True):
            mod.main(["check-opencode"])
        with patch.object(mod, "opencode_v2_installed", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "unsupported version"):
                mod.main(["check-opencode"])

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
