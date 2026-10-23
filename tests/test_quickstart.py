"""Keep the Quickstart's make commands consistent with the Makefile."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QuickstartDocsTests(unittest.TestCase):
    def test_readme_links_to_quickstart(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("[QUICKSTART.md](QUICKSTART.md)", readme)

    def test_quickstart_make_commands_are_defined(self):
        mk = (ROOT / "Makefile").read_text(encoding="utf-8")
        targets = set(re.findall(r"^([a-zA-Z][a-zA-Z0-9_-]*):", mk, re.MULTILINE))
        qs = (ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
        commands = re.findall(r"(?m)^\s*make\s+([a-z][a-z0-9_-]*)\b", qs)
        commands += re.findall(r"`make\s+([a-z][a-z0-9_-]*)\b", qs)
        self.assertTrue(commands, "No Makefile invocations found in Quickstart")
        self.assertEqual([], sorted(set(commands) - targets))

    def test_commands_cover_existing_install_and_service_modes(self):
        guide = (ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
        for command in ("make doctor", "make server", "make ready",
                        "make configure-opencode", "make service-install",
                        "make service-start", "make install-bonsai"):
            with self.subTest(command=command):
                self.assertIn(command, guide)


if __name__ == "__main__":
    unittest.main()
