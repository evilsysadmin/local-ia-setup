"""Integration: Bash commands and Python share the same OpenCode V2 gate.

Fake executables live only in a temporary PATH; no browser, server or installer.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "local-ia"


class OpenCodeShellTests(unittest.TestCase):
    def invoke(self, action: str, version: str):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            opencode = root / "opencode"
            opencode.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = '--version' ]; then\n"
                f"  printf '%s\\n' '{version}'\n"
                "else\n"
                "  echo OPENCODE_STARTED_FOR_TEST\n"
                "fi\n",
                encoding="utf-8",
            )
            opencode.chmod(0o755)
            curl = root / "curl"
            curl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            curl.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = str(root) + os.pathsep + os.environ.get("PATH", "")
            return subprocess.run(
                ["bash", str(RUNNER), action], env=env,
                text=True, capture_output=True, timeout=15,
            )

    def test_actual_v213_launches_without_reinstall(self):
        result = self.invoke("opencode", "opencode v2.1.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OPENCODE_STARTED_FOR_TEST", result.stdout)

    def test_installer_does_not_run_for_installed_v213(self):
        result = self.invoke("install-opencode", "opencode v2.1.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already installed", result.stdout)
        self.assertNotIn("Running downloaded", result.stdout)

    def test_legacy_version_is_rejected(self):
        result = self.invoke("opencode", "opencode v1.9.9")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires OpenCode V2", result.stderr)
        self.assertNotIn("OPENCODE_STARTED_FOR_TEST", result.stdout)


if __name__ == "__main__":
    unittest.main()
