"""No-GPU tests for local-only agent preflight and Git branch safety."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import agent_launcher as agent


def repo(tmp):
    root = Path(tmp) / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@invalid.example"], check=True)
    (root / "README.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "initial"], check=True)
    return root


class AgentLauncherTests(unittest.TestCase):
    def test_requires_git_project(self):
        with self.assertRaisesRegex(ValueError, "Missing PROJECT"):
            agent.resolve_project(None)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Git worktree"):
                agent.resolve_project(tmp)

    def test_plan_allows_dirty_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            (root / "untracked.txt").write_text("pending")
            self.assertEqual(agent.resolve_project(str(root)), root)
            self.assertEqual(agent.check_worktree(root, "plan"), ("main", 1))

    def test_build_requires_clean_feature_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            with self.assertRaisesRegex(ValueError, "Build refused on"):
                agent.check_worktree(root, "build")
            subprocess.run(["git", "-C", str(root), "checkout", "-qb", "feat/bonsai"], check=True)
            self.assertEqual(agent.check_worktree(root, "build"), ("feat/bonsai", 0))
            (root / "untracked.txt").write_text("local changes")
            with self.assertRaisesRegex(ValueError, "pending change"):
                agent.check_worktree(root, "build")

    def test_detached_head_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            subprocess.run(["git", "-C", str(root), "checkout", "-q", "--detach"], check=True)
            with self.assertRaisesRegex(ValueError, "Detached HEAD"):
                agent.check_worktree(root, "plan")

    def test_requires_local_provider_and_live_model(self):
        cfg = agent.local_setup.generate_config(
            "bonsai-model", 32768, 4096, 2048, 12288, "http://127.0.0.1:8080")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opencode.json"
            path.write_text(json.dumps(cfg))
            agent.validate_config(path, "bonsai-model", "http://127.0.0.1:8080", 32768)
            with self.assertRaisesRegex(ValueError, "model ID differs"):
                agent.validate_config(path, "wrong", "http://127.0.0.1:8080", 32768)
            with self.assertRaisesRegex(ValueError, "context differs"):
                agent.validate_config(path, "bonsai-model", "http://127.0.0.1:8080", 8192)
            cfg["policies"] = []
            path.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError, "policy missing"):
                agent.validate_config(path, "bonsai-model", "http://127.0.0.1:8080", 32768)


    def test_main_launches_server_before_opencode_only_for_valid_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            with patch.object(agent, "resolve_project", return_value=root), \
                 patch.object(agent, "check_worktree", return_value=("main", 0)), \
                 patch.object(agent.local_setup, "opencode_v2_installed", return_value=True), \
                 patch.object(agent.compose_lifecycle, "up", return_value="started") as start, \
                 patch.object(agent, "preflight", return_value=root), \
                 patch.object(agent.os, "execvp", side_effect=RuntimeError("exec intercepted")):
                with patch.dict("os.environ", {"PROJECT": str(root), "BONSAI_READY_TIMEOUT": "20",
                                             "BONSAI_DIR": "/tmp/demo"}):
                    with self.assertRaisesRegex(RuntimeError, "exec intercepted"):
                        agent.main(["plan", "http://127.0.0.1:8080", "32768"])
                start.assert_called_once_with("http://127.0.0.1:8080", 32768, 20.0, Path("/tmp/demo"))

    def test_main_does_not_start_server_if_opencode_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            with patch.object(agent, "resolve_project", return_value=root), \
                 patch.object(agent, "check_worktree", return_value=("main", 0)), \
                 patch.object(agent.local_setup, "opencode_v2_installed", return_value=False), \
                 patch.object(agent.compose_lifecycle, "up") as start:
                with patch.dict("os.environ", {"PROJECT": str(root)}):
                    with self.assertRaisesRegex(RuntimeError, "OpenCode V2 not found"):
                        agent.main(["plan", "http://127.0.0.1:8080", "32768"])
                start.assert_not_called()


    def test_deep_variant_requires_configuration_before_any_gpu_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            p = Path(tmp) / ".config/opencode/opencode.json"
            p.parent.mkdir(parents=True)
            cfg = agent.local_setup.generate_config(
                "bonsai-model", 32768, 4096, 2048, 12288, "http://127.0.0.1:8080")
            model = cfg["providers"]["bonsai-local"]["models"]["bonsai"]
            model.pop("body")
            model.pop("variants")
            p.write_text(json.dumps(cfg))
            with patch.object(agent.Path, "home", return_value=Path(tmp)), \
                 patch.object(agent, "resolve_project", return_value=root), \
                 patch.object(agent, "check_worktree", return_value=("main", 0)), \
                 patch.object(agent.compose_lifecycle, "up") as start:
                with self.assertRaisesRegex(ValueError, "configure-reasoning"):
                    agent.main(["plan", "http://127.0.0.1:8080", "32768", "deep"])
                start.assert_not_called()

    def test_deep_variant_passes_model_selector_to_opencode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            p = Path(tmp) / ".config/opencode/opencode.json"
            p.parent.mkdir(parents=True)
            cfg = agent.local_setup.generate_config(
                "bonsai-model", 32768, 4096, 2048, 12288, "http://127.0.0.1:8080")
            p.write_text(json.dumps(cfg))
            with patch.object(agent.Path, "home", return_value=Path(tmp)), \
                 patch.object(agent, "resolve_project", return_value=root), \
                 patch.object(agent, "check_worktree", return_value=("main", 0)), \
                 patch.object(agent.local_setup, "opencode_v2_installed", return_value=True), \
                 patch.object(agent.compose_lifecycle, "up", return_value="reused") as start, \
                 patch.object(agent, "preflight", return_value=root) as preflight, \
                 patch.object(agent.os, "chdir"), \
                 patch.object(agent.os, "execvp", side_effect=RuntimeError("intercepted")) as execvp:
                with patch.dict("os.environ", {"PROJECT": str(root), "BONSAI_DIR": tmp,
                                               "BONSAI_READY_TIMEOUT": "120"}):
                    with self.assertRaisesRegex(RuntimeError, "intercepted"):
                        agent.main(["plan", "http://127.0.0.1:8080", "32768", "deep"])
                start.assert_called_once()
                self.assertTrue(preflight.call_args.kwargs["require_deep"])
                execvp.assert_called_once_with("opencode", [
                    "opencode", "--model", "bonsai-local/bonsai#deep", "--agent", "plan",
                ])

    def test_default_model_keeps_original_selector_without_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            with patch.object(agent, "resolve_project", return_value=root), \
                 patch.object(agent, "check_worktree", return_value=("main", 0)), \
                 patch.object(agent.local_setup, "opencode_v2_installed", return_value=True), \
                 patch.object(agent.compose_lifecycle, "up", return_value="reused"), \
                 patch.object(agent, "preflight", return_value=root) as preflight, \
                 patch.object(agent.os, "chdir"), \
                 patch.object(agent.os, "execvp", side_effect=RuntimeError("intercepted")) as execvp:
                with patch.dict("os.environ", {"PROJECT": str(root), "BONSAI_DIR": tmp}):
                    with self.assertRaisesRegex(RuntimeError, "intercepted"):
                        agent.main(["build", "http://127.0.0.1:8080", "32768"])
                self.assertFalse(preflight.call_args.kwargs["require_deep"])
                execvp.assert_called_once_with("opencode", [
                    "opencode", "--model", "bonsai-local/bonsai", "--agent", "build",
                ])

    def test_preflight_rejects_config_override_env(self):
        with patch.dict("os.environ", {"OPENCODE_CONFIG_CONTENT": "{}"}):
            with self.assertRaisesRegex(ValueError, "OPENCODE_CONFIG_CONTENT"):
                agent.preflight("/tmp/unused", "plan", "http://127.0.0.1:8080", 32768)

    def test_preflight_no_exec_and_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp)
            cfg = Path(tmp) / "opencode.json"
            good = agent.local_setup.generate_config(
                "test", 32768, 4096, 2048, 12288, "http://127.0.0.1:8080")
            cfg.write_text(json.dumps(good))
            with patch.object(agent.local_setup, "wait_until_ready", return_value="test"), \
                    patch.object(agent.local_setup, "check_server_context") as context, \
                    patch.object(agent.local_setup, "opencode_v2_installed", return_value=True), \
                    patch.object(agent.shutil, "which", return_value="/usr/bin/opencode"), \
                    patch.dict("os.environ", {k: "" for k in agent.OVERRIDES}):
                self.assertEqual(agent.preflight(str(root), "plan", "http://127.0.0.1:8080", 32768, cfg), root)
                context.assert_called_once_with("http://127.0.0.1:8080", 32768)
            self.assertEqual(agent.git("status", "--porcelain", cwd=root), "")


if __name__ == "__main__":
    unittest.main()
