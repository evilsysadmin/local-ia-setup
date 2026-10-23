"""No daemon, no GPU: lifecycle checks with all effects mocked."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lifecycle


class LifecycleTests(unittest.TestCase):
    BASE = "http://127.0.0.1:8080"
    DEMO = Path("/tmp/fake-bonsai-demo")

    def test_reuses_healthy_server_without_touching_systemd(self):
        with patch.object(lifecycle, "listener_present", return_value=True), \
             patch.object(lifecycle, "verify_ready", return_value="Ternary-Bonsai-2-27B.gguf"), \
             patch.object(lifecycle.user_service, "install") as install, \
             patch.object(lifecycle.user_service, "systemctl") as systemctl:
            self.assertEqual(lifecycle.up(self.BASE, 32768, 30, self.DEMO), "reused")
            install.assert_not_called()
            systemctl.assert_not_called()

    def test_if_service_active_waits_without_restarting(self):
        with patch.object(lifecycle, "listener_present", return_value=False), \
             patch.object(lifecycle, "managed_active", return_value=True), \
             patch.object(lifecycle, "verify_ready") as ready, \
             patch.object(lifecycle.user_service, "install") as install:
            self.assertEqual(lifecycle.up(self.BASE, 32768, 30, self.DEMO), "managed")
            ready.assert_called_once_with(self.BASE, 32768, 30)
            install.assert_not_called()

    def test_does_not_duplicate_an_unresponsive_cuda_process(self):
        with patch.object(lifecycle, "listener_present", return_value=False), \
             patch.object(lifecycle, "managed_active", return_value=False), \
             patch.object(lifecycle, "matching_bonsai_pids", return_value=[350930]), \
             patch.object(lifecycle.user_service, "install") as install, \
             patch.object(lifecycle.user_service, "systemctl") as systemctl:
            with self.assertRaisesRegex(RuntimeError, "350930"):
                lifecycle.up(self.BASE, 32768, 30, self.DEMO)
            install.assert_not_called()
            systemctl.assert_not_called()

    def test_install_and_start_without_enabling_login_autostart(self):
        with patch.object(lifecycle, "listener_present", return_value=False), \
             patch.object(lifecycle, "managed_active", side_effect=[False, True]), \
             patch.object(lifecycle, "matching_bonsai_pids", return_value=[]), \
             patch.object(lifecycle, "verify_ready") as ready, \
             patch.object(lifecycle.user_service, "install", return_value="Installed") as install, \
             patch.object(lifecycle.user_service, "systemctl") as systemctl:
            self.assertEqual(lifecycle.up(self.BASE, 32768, 30, self.DEMO), "started")
            install.assert_called_once()
            systemctl.assert_called_once_with("start", lifecycle.user_service.NAME)
            ready.assert_called_once_with(self.BASE, 32768, 30)

    def test_down_never_stops_an_unmanaged_server(self):
        with patch.object(lifecycle.user_service, "check_ours", return_value=False), \
             patch.object(lifecycle.user_service, "systemctl") as systemctl:
            self.assertEqual(lifecycle.down(self.BASE), "not-installed")
            systemctl.assert_not_called()

    def test_down_stops_only_managed_unit(self):
        with patch.object(lifecycle.user_service, "check_ours", return_value=True), \
             patch.object(lifecycle, "managed_active", return_value=True), \
             patch.object(lifecycle, "listener_present", return_value=False), \
             patch.object(lifecycle.user_service, "systemctl") as systemctl:
            self.assertEqual(lifecycle.down(self.BASE), "stopped")
            systemctl.assert_called_once_with("stop", lifecycle.user_service.NAME)

    def test_rejects_unexpected_remote_model(self):
        with patch.object(lifecycle.local_setup, "wait_until_ready", return_value="Other-Model"), \
             patch.object(lifecycle.local_setup, "check_server_context") as ctx:
            with self.assertRaisesRegex(RuntimeError, "unexpected model"):
                lifecycle.verify_ready(self.BASE, 32768, 20)
            ctx.assert_not_called()

    def test_wait_failure_has_actionable_log_command(self):
        with patch.object(lifecycle, "listener_present", return_value=False), \
             patch.object(lifecycle, "managed_active", return_value=False), \
             patch.object(lifecycle, "matching_bonsai_pids", return_value=[]), \
             patch.object(lifecycle.user_service, "install", return_value="Installed"), \
             patch.object(lifecycle.user_service, "systemctl"), \
             patch.object(lifecycle, "verify_ready", side_effect=RuntimeError("timed out")):
            with self.assertRaisesRegex(RuntimeError, "make service-logs"):
                lifecycle.up(self.BASE, 32768, 20, self.DEMO)

    def test_validation_precedes_install(self):
        with patch.object(lifecycle.user_service, "install") as install:
            with self.assertRaises(ValueError):
                lifecycle.up("https://example.org:443", 32768, 30, self.DEMO)
            with self.assertRaises(ValueError):
                lifecycle.up(self.BASE, 32768, -3, self.DEMO)
            install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
