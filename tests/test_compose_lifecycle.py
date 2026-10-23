"""Container orchestration tests. Never contact a real Docker daemon."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import compose_lifecycle as ctl


class ComposeLifecycleTests(unittest.TestCase):
    BASE = "http://127.0.0.1:8080"
    DEMO = Path("/tmp/bonsai-demo-for-test")

    def test_reuses_healthy_existing_server_without_docker(self):
        with patch.object(ctl.lifecycle, "listener_present", return_value=True), \
             patch.object(ctl.lifecycle, "verify_ready") as ready, \
             patch.object(ctl, "docker_available") as docker:
            self.assertEqual(ctl.up(self.BASE, 32768, 120, self.DEMO), "reused")
            ready.assert_called_once()
            docker.assert_not_called()

    def test_reuses_native_unit_without_docker(self):
        with patch.object(ctl.lifecycle, "listener_present", return_value=False), \
             patch.object(ctl.lifecycle, "managed_active", return_value=True), \
             patch.object(ctl.lifecycle, "verify_ready"), \
             patch.object(ctl, "docker_available") as docker:
            self.assertEqual(ctl.up(self.BASE, 32768, 120, self.DEMO), "native")
            docker.assert_not_called()

    def test_orphan_does_not_start_compose(self):
        with patch.object(ctl.lifecycle, "listener_present", return_value=False), \
             patch.object(ctl.lifecycle, "managed_active", return_value=False), \
             patch.object(ctl, "docker_available"), \
             patch.object(ctl, "existing_container", return_value=None), \
             patch.object(ctl.lifecycle, "matching_bonsai_pids", return_value=[350930]), \
             patch.object(ctl, "compose") as docker:
            with self.assertRaisesRegex(RuntimeError, "350930"):
                ctl.up(self.BASE, 32768, 120, self.DEMO)
            docker.assert_not_called()

    def test_start_owned_container_and_wait_until_ready(self):
        with patch.object(ctl.lifecycle, "listener_present", return_value=False), \
             patch.object(ctl.lifecycle, "managed_active", return_value=False), \
             patch.object(ctl, "docker_available"), \
             patch.object(ctl, "existing_container", side_effect=[None, "container-id"]), \
             patch.object(ctl.lifecycle, "matching_bonsai_pids", return_value=[]), \
             patch.object(ctl, "check_demo"), \
             patch.object(ctl, "compose") as docker, \
             patch.object(ctl.lifecycle, "verify_ready") as ready:
            self.assertEqual(ctl.up(self.BASE, 32768, 120, self.DEMO), "started")
            docker.assert_called_once_with("up", "-d", "--build", "--no-deps", "bonsai", timeout=600)
            ready.assert_called_once_with(self.BASE, 32768, 120)

    def test_down_without_owned_container_is_noop(self):
        with patch.object(ctl, "docker_available"), \
             patch.object(ctl, "existing_container", return_value=None), \
             patch.object(ctl, "compose") as docker:
            self.assertEqual(ctl.down(self.BASE, self.DEMO), "absent")
            docker.assert_not_called()

    def test_down_owns_service_before_stopping(self):
        with patch.object(ctl, "docker_available"), \
             patch.object(ctl, "existing_container", return_value="container-id"), \
             patch.object(ctl, "compose") as docker:
            self.assertEqual(ctl.down(self.BASE, self.DEMO), "stopped")
            docker.assert_called_once_with("down", "--timeout", "40", timeout=90)

    def test_down_refuses_unexpected_owner_without_stopping(self):
        with patch.object(ctl, "docker_available"), \
             patch.object(ctl, "existing_container", side_effect=RuntimeError("Unexpected owner")), \
             patch.object(ctl, "compose") as docker:
            with self.assertRaisesRegex(RuntimeError, "Unexpected owner"):
                ctl.down(self.BASE, self.DEMO)
            docker.assert_not_called()

    def test_container_identity_validated_by_labels_mount_and_read_only(self):
        labels = {
            "com.docker.compose.project": ctl.PROJECT,
            "com.docker.compose.service": ctl.SERVICE,
            ctl.LABEL: ctl.LABEL_VALUE,
        }
        good = [{"Config": {"Labels": labels}, "Mounts": [
            {"Destination": "/bonsai", "Source": str(self.DEMO), "RW": False}
        ]}]
        with patch.object(ctl, "compose", return_value="container-id"), \
             patch.object(ctl, "call", return_value=json.dumps(good)):
            self.assertEqual(ctl.existing_container(self.DEMO), "container-id")
        good[0]["Mounts"][0]["RW"] = True
        with patch.object(ctl, "compose", return_value="container-id"), \
             patch.object(ctl, "call", return_value=json.dumps(good)):
            with self.assertRaisesRegex(RuntimeError, "Refusing"):
                ctl.existing_container(self.DEMO)

    def test_docker_preflight_rejects_missing_cli(self):
        with patch.object(ctl.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Docker missing"):
                ctl.docker_available()

    def test_rejects_invalid_remote_endpoint_before_start(self):
        with patch.object(ctl, "docker_available") as docker:
            with self.assertRaises(ValueError):
                ctl.up("http://0.0.0.0:8080", 32768, 120, self.DEMO)
            docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
