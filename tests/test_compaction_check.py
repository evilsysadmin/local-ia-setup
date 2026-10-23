"""Compaction audit: no inference, no writes, static and live consistency."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import compaction_check as check
import local_setup


def cfg():
    return local_setup.generate_config(
        "PrismML-Bonsai", 32768, 4096, 2048, 12288, "http://127.0.0.1:8080"
    )


class CompactionCheckTests(unittest.TestCase):
    def test_valid_same_gguf_separate_output_and_buffer(self):
        errors, notes = check.inspect_config(cfg(), "http://127.0.0.1:8080", 32768)
        self.assertEqual(errors, [])
        self.assertTrue(any("12,288" in note for note in notes))
        self.assertTrue(any("4,096" in note for note in notes))

    def test_old_buffer_or_alias_rejected_with_repair_advice(self):
        source = cfg()
        source["compaction"]["buffer"] = 4096
        errors, _ = check.inspect_config(source, "http://127.0.0.1:8080", 32768)
        self.assertTrue(any("fix-compaction" in error for error in errors))
        source = cfg()
        source["providers"]["bonsai-local"]["models"]["bonsai-summary"]["limit"]["output"] = 4096
        errors, _ = check.inspect_config(source, "http://127.0.0.1:8080", 32768)
        self.assertTrue(any("fix-compaction" in error for error in errors))

    def test_live_mismatch_and_context_mismatch_detected_without_completion(self):
        data = cfg()
        def fake(url, timeout=3):
            if url.endswith("/health"):
                return {"status": "ok"}
            return {"n_ctx_slot": 16384}
        with patch.object(check.local_setup, "fetch_json", side_effect=fake) as fetch, \
             patch.object(check.local_setup, "model_id", return_value="foreign"):
            errors, _ = check.check_server("http://127.0.0.1:8080", data, 32768)
            self.assertEqual(len(errors), 2)
            self.assertTrue(all(
                url.endswith(("/health", "/props")) for (url,), _ in
                ((c.args, c.kwargs) for c in fetch.call_args_list)
            ))

    def test_offline_does_not_fail_static_or_launch_server(self):
        data = cfg()
        with patch.object(check.local_setup, "fetch_json", side_effect=OSError("offline")), \
             redirect_stdout(io.StringIO()) as out:
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "opencode.json"
                path.write_text(json.dumps(data))
                before = path.read_bytes()
                self.assertTrue(check.run("http://127.0.0.1:8080", 32768, path))
                self.assertEqual(path.read_bytes(), before)
        self.assertIn("static config check only", out.getvalue())
        self.assertIn("No inference request generated", out.getvalue())

    def test_project_overrides_and_external_url_not_silently_verified(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "project"
            root.mkdir()
            (root / "opencode.json").write_text('{"model":"other/provider"}')
            with patch.dict("os.environ", {"OPENCODE_CONFIG_CONTENT": "SECRET"}, clear=True):
                warnings = check.warnings_for_overrides(str(root))
            self.assertEqual(len(warnings), 2)
            self.assertNotIn("SECRET", " ".join(warnings))
        with self.assertRaises(ValueError):
            check.run("http://example.com:8080", 32768, Path("/nonexistent"))

    def test_symlink_and_oversized_config_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = root / "data.json"
            data.write_text("{}")
            link = root / "config.json"
            link.symlink_to(data)
            with self.assertRaisesRegex(ValueError, "symlinked"):
                check.config_read(link)
            data.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "large"):
                check.config_read(data)

    def test_auto_disabled_not_overridden(self):
        data = cfg()
        data["compaction"]["auto"] = False
        errors, notes = check.inspect_config(data, "http://127.0.0.1:8080", 32768)
        self.assertEqual(errors, [])
        self.assertIn("NOTE: automatic compaction is disabled by user preference", notes)


if __name__ == "__main__":
    unittest.main()
