"""Llama status: no inference, graceful missing metrics, safe opt-in logs."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import llama_status as ls


class LlamaStatusTests(unittest.TestCase):
    BASE = "http://127.0.0.1:8080"

    def test_metrics_parse_and_format(self):
        metrics = ls.parse_metrics(
            "# HELP tokens generated\n"
            'llamacpp:requests_processing 1\n'
            'llamacpp:requests_deferred 2\n'
            'llamacpp:prompt_tokens_total 120\n'
            'llamacpp:tokens_predicted_total 300\n'
            'llamacpp:predicted_tokens_seconds 48.75\n'
            'llamacpp:kv_cache_usage_ratio 0.25\n'
            'llamacpp:ignored_total 999\n'
        )
        self.assertEqual(metrics["llamacpp:tokens_predicted_total"], 300)
        self.assertNotIn("llamacpp:ignored_total", metrics)
        self.assertEqual(ls.format_metric("llamacpp:predicted_tokens_seconds", 48.75),
                         "Generation throughput (server): 48.8 tok/s")
        self.assertEqual(ls.format_metric("llamacpp:kv_cache_usage_ratio", .25),
                         "KV cache usage: 25.0%")

    def test_disabled_metrics_fails_softly(self):
        from urllib.error import HTTPError
        with patch.object(ls, "urlopen", side_effect=HTTPError(self.BASE, 501, "off", {}, None)):
            values, why = ls.get_metrics(self.BASE)
        self.assertEqual(values, {})
        self.assertIn("disabled", why)

    def test_metrics_read_is_get_bounded_and_loopback_only(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, maximum):
                assert maximum == 256 * 1024 + 1
                return b"llamacpp:tokens_predicted_total 12\n"
        with patch.object(ls, "urlopen", return_value=Response()) as opened:
            values, err = ls.get_metrics(self.BASE)
            self.assertIsNone(err)
            self.assertEqual(values["llamacpp:tokens_predicted_total"], 12)
            req = opened.call_args.args[0]
            self.assertEqual(req.full_url, self.BASE + "/metrics")
            self.assertEqual(req.get_method(), "GET")
        with self.assertRaises(ValueError):
            ls.get_metrics("http://example.org:8080")

    def test_snapshot_does_not_generate_completion(self):
        with patch.object(ls.local_setup, "fetch_json", return_value={"status": "ok"}), \
             patch.object(ls.local_setup, "model_id", return_value="Bonsai"), \
             patch.object(ls, "get_context", return_value=32768), \
             patch.object(ls, "get_metrics", return_value=(
                 {"llamacpp:requests_processing": 1, "llamacpp:tokens_predicted_total": 123},
                 None)), \
             patch.object(ls, "nvidia_memory", return_value=None), \
             redirect_stdout(io.StringIO()) as output:
            self.assertTrue(ls.snapshot(self.BASE, 32768))
        self.assertIn("Generated tokens (since start): 123", output.getvalue())
        self.assertIn("Requests processing: 1", output.getvalue())

    def test_offline_snapshot_no_metrics_exception(self):
        with patch.object(ls.local_setup, "fetch_json", side_effect=OSError("connection refused")), \
             patch.object(ls, "get_metrics") as metrics, \
             redirect_stdout(io.StringIO()) as output:
            self.assertFalse(ls.snapshot(self.BASE, 32768))
            self.assertIn("OFFLINE", output.getvalue())
            metrics.assert_not_called()

    def test_logs_disabled_by_default(self):
        with patch.object(ls.compose_lifecycle, "docker_available") as available, \
             patch.object(ls.compose_lifecycle, "compose") as compose:
            ls.show_logs(Path("/fake"), 0, False)
            available.assert_not_called()
            compose.assert_not_called()

    def test_tail_bounded_owned_compose_only(self):
        with patch.object(ls.compose_lifecycle, "docker_available"), \
             patch.object(ls.compose_lifecycle, "existing_container", return_value="own") as owned, \
             patch.object(ls.compose_lifecycle, "compose", return_value="last line") as call, \
             redirect_stdout(io.StringIO()) as output:
            ls.show_logs(Path("/fake"), 50, False)
            owned.assert_called_once()
            call.assert_called_once_with("logs", "--no-color", "--tail", "50",
                                         "bonsai", timeout=20)
            self.assertIn("last line", output.getvalue())

    def test_logs_refuses_unowned_compose(self):
        with patch.object(ls.compose_lifecycle, "docker_available"), \
             patch.object(ls.compose_lifecycle, "existing_container", return_value=None), \
             patch.object(ls.compose_lifecycle, "compose") as compose:
            ls.show_logs(Path("/fake"), 50, False)
            compose.assert_not_called()

    def test_follow_uses_no_timeout_and_only_owned_logs(self):
        import subprocess
        with patch.object(ls.compose_lifecycle, "docker_available"), \
             patch.object(ls.compose_lifecycle, "existing_container", return_value="own"), \
             patch.object(ls.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as call, \
             redirect_stdout(io.StringIO()):
            ls.show_logs(Path("/fake"), 0, True)
            args = call.call_args.args[0]
            self.assertEqual(args[-5:], ["--follow", "--no-color", "--tail", "30", "bonsai"])
            self.assertNotIn("timeout", call.call_args.kwargs)

    def test_args_bounded_and_validate_follow(self):
        with patch.object(ls, "snapshot") as status, patch.object(ls, "show_logs") as logs:
            for tail in ("-1", "1001", "x"):
                with self.assertRaisesRegex(ValueError, "TAIL"):
                    ls.main([self.BASE, "32768", "/tmp", tail, "0"])
            with self.assertRaisesRegex(ValueError, "FOLLOW"):
                ls.main([self.BASE, "32768", "/tmp", "0", "yes"])
            status.assert_not_called()
            logs.assert_not_called()
            ls.main([self.BASE, "32768", "/tmp", "10", "1"])
            logs.assert_called_once_with(Path("/tmp"), 10, True)


if __name__ == "__main__":
    unittest.main()
