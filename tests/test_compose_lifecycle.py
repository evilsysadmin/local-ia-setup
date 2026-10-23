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
             patch.object(ctl, "gpu_check") as gpu, \
             patch.object(ctl, "compose") as docker, \
             patch.object(ctl.lifecycle, "verify_ready") as ready:
            self.assertEqual(ctl.up(self.BASE, 32768, 120, self.DEMO), "started")
            docker.assert_called_once_with("up", "-d", "--build", "--no-deps", "bonsai", timeout=600)
            gpu.assert_called_once_with()
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


    def test_gpu_check_runs_disposable_nvidia_container(self):
        output = "0, NVIDIA RTX, 12288 MiB"
        with patch.object(ctl, "docker_available") as docker, \
             patch.object(ctl, "call", return_value=output) as call:
            self.assertEqual(ctl.gpu_check(), output)
            docker.assert_called_once_with()
            args, kwargs = call.call_args
            self.assertEqual(
                args[0],
                ["docker", "run", "--rm", "--gpus", "all", "--pull=missing",
                 ctl.GPU_TEST_IMAGE, "nvidia-smi",
                 "--query-gpu=index,name,memory.total", "--format=csv,noheader"],
            )
            self.assertEqual(kwargs, {"timeout": 240})
            self.assertNotIn("--privileged", args[0])
            self.assertNotIn("-v", args[0])

    def test_gpu_check_fails_when_container_cannot_see_gpu(self):
        with patch.object(ctl, "docker_available"), \
             patch.object(ctl, "call", side_effect=RuntimeError("no compatible GPU runtime")):
            with self.assertRaisesRegex(RuntimeError, "NVIDIA Container Toolkit"):
                ctl.gpu_check()

    def test_gpu_check_fails_on_empty_nvidia_smi(self):
        with patch.object(ctl, "docker_available"), \
             patch.object(ctl, "call", return_value="  "):
            with self.assertRaisesRegex(RuntimeError, "reported no GPUs"):
                ctl.gpu_check()

    def test_new_compose_launch_refuses_when_gpu_probe_fails(self):
        with patch.object(ctl.lifecycle, "listener_present", return_value=False), \
             patch.object(ctl.lifecycle, "managed_active", return_value=False), \
             patch.object(ctl, "docker_available"), \
             patch.object(ctl, "existing_container", return_value=None), \
             patch.object(ctl.lifecycle, "matching_bonsai_pids", return_value=[]), \
             patch.object(ctl, "check_demo"), \
             patch.object(ctl, "gpu_check", side_effect=RuntimeError("NVIDIA Container Toolkit")), \
             patch.object(ctl, "compose") as compose:
            with self.assertRaisesRegex(RuntimeError, "NVIDIA Container Toolkit"):
                ctl.up(self.BASE, 32768, 120, self.DEMO)
            compose.assert_not_called()

    def test_orphan_blocks_gpu_image_pull(self):
        with patch.object(ctl.lifecycle, "listener_present", return_value=False), \
             patch.object(ctl.lifecycle, "managed_active", return_value=False), \
             patch.object(ctl, "docker_available"), \
             patch.object(ctl, "existing_container", return_value=None), \
             patch.object(ctl.lifecycle, "matching_bonsai_pids", return_value=[350930]), \
             patch.object(ctl, "gpu_check") as gpu:
            with self.assertRaisesRegex(RuntimeError, "350930"):
                ctl.up(self.BASE, 32768, 120, self.DEMO)
            gpu.assert_not_called()

    def test_probe_image_matches_cuda_runtime_major_minor(self):
        dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04", dockerfile)
        self.assertEqual(ctl.GPU_TEST_IMAGE, "nvidia/cuda:12.8.1-base-ubuntu24.04")

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
