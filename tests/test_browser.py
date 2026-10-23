"""Browser launcher uses only loopback and never starts a server itself."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import browser


class BrowserTests(unittest.TestCase):
    BASE = "http://127.0.0.1:8080"

    def test_opens_default_desktop_browser_after_ready(self):
        with patch.object(browser.local_setup, "wait_until_ready", return_value="Ternary-Bonsai-2-27B.gguf") as ready, \
             patch.object(browser.shutil, "which", side_effect=lambda cmd: "/usr/bin/xdg-open" if cmd == "xdg-open" else None), \
             patch.object(browser.subprocess, "Popen") as spawn:
            self.assertEqual(browser.open_browser(self.BASE), self.BASE)
            ready.assert_called_once_with(self.BASE, timeout=5, interval=1)
            self.assertEqual(spawn.call_args.args[0], ["xdg-open", self.BASE])
            self.assertTrue(spawn.call_args.kwargs["start_new_session"])
            self.assertNotIn("shell", spawn.call_args.kwargs)

    def test_falls_back_to_gio(self):
        with patch.object(browser.local_setup, "wait_until_ready", return_value="Bonsai 2"), \
             patch.object(browser.shutil, "which", side_effect=lambda cmd: "/usr/bin/gio" if cmd == "gio" else None), \
             patch.object(browser.subprocess, "Popen") as spawn:
            browser.open_browser(self.BASE)
            self.assertEqual(spawn.call_args.args[0], ["gio", "open", self.BASE])

    def test_no_server_gives_actionable_error_without_opening(self):
        with patch.object(browser.local_setup, "wait_until_ready", side_effect=RuntimeError("not ready")), \
             patch.object(browser.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "make up"):
                browser.open_browser(self.BASE)
            spawn.assert_not_called()

    def test_refuses_other_local_model(self):
        with patch.object(browser.local_setup, "wait_until_ready", return_value="unrelated-model"), \
             patch.object(browser.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "not Bonsai"):
                browser.open_browser(self.BASE)
            spawn.assert_not_called()

    def test_rejects_external_address_without_opening(self):
        with patch.object(browser.local_setup, "wait_until_ready") as ready, \
             patch.object(browser.subprocess, "Popen") as spawn:
            with self.assertRaises(ValueError):
                browser.open_browser("http://example.com:8080")
            ready.assert_not_called()
            spawn.assert_not_called()

    def test_missing_desktop_opener_gives_manual_url(self):
        with patch.object(browser.local_setup, "wait_until_ready", return_value="Bonsai"), \
             patch.object(browser.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Open http://127.0.0.1:8080 manually"):
                browser.open_browser(self.BASE)


if __name__ == "__main__":
    unittest.main()
