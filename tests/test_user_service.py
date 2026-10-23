"""Systemd user unit generation/ownership tests; do not contact the user bus."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("user_service", ROOT / "scripts/user_service.py")
svc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(svc)


class UserServiceTests(unittest.TestCase):
    def test_unit_runs_repo_launcher_not_bonsai_binary(self):
        text = svc.render_unit(ROOT)
        self.assertTrue(text.startswith(svc.MARKER))
        self.assertIn('ExecStart=/usr/bin/bash ', text)
        self.assertIn('/scripts/local-ia" server', text)
        self.assertIn('Type=exec', text)
        self.assertIn('WantedBy=default.target', text)
        self.assertIn('KillSignal=SIGINT', text)
        self.assertNotIn('EnvironmentFile=', text)
        self.assertNotIn('ExecStartPre=sudo', text)

    def test_quote_handles_spaces_quotes_and_percent(self):
        with tempfile.TemporaryDirectory(prefix='local ia % space ') as tmp:
            repo = Path(tmp) / 'odd"name'
            runner = repo / 'scripts' / 'local-ia'
            runner.parent.mkdir(parents=True)
            runner.write_text('#!/bin/bash\n')
            unit = svc.render_unit(repo)
            self.assertIn('local ia %% space', unit)
            self.assertIn('odd\\"name', unit)
        for bad in ('', 'x\nExecStop=/usr/bin/false', 'x\0y'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                svc.quote_unit_arg(bad)

    def test_install_idempotent_and_does_not_start_or_enable(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(svc, 'systemctl') as ctl:
            unit = Path(tmp) / svc.NAME
            self.assertEqual(svc.install(ROOT, unit), 'Installed')
            self.assertEqual(svc.install(ROOT, unit), 'Unchanged')
            self.assertEqual(ctl.call_count, 1)
            ctl.assert_called_with('daemon-reload')
            self.assertEqual(unit.stat().st_mode & 0o777, 0o644)

    def test_existing_unmanaged_unit_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(svc, 'systemctl') as ctl:
            unit = Path(tmp) / svc.NAME
            unit.write_text('[Service]\nExecStart=/usr/bin/true\n')
            with self.assertRaisesRegex(RuntimeError, 'unmanaged'):
                svc.install(ROOT, unit)
            with self.assertRaisesRegex(RuntimeError, 'unmanaged'):
                svc.uninstall(unit)
            self.assertEqual(unit.read_text(), '[Service]\nExecStart=/usr/bin/true\n')
            ctl.assert_not_called()

    def test_uninstall_requires_ownership_and_disables_first(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(svc, 'systemctl') as ctl:
            unit = Path(tmp) / svc.NAME
            self.assertEqual(svc.uninstall(unit), 'Not installed')
            svc.install(ROOT, unit)
            ctl.reset_mock()
            self.assertEqual(svc.uninstall(unit), 'Uninstalled')
            self.assertFalse(unit.exists())
            self.assertEqual(ctl.call_args_list[0].args, ('disable', '--now', svc.NAME))
            self.assertEqual(ctl.call_args_list[1].args, ('daemon-reload',))

    def test_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(svc, 'systemctl') as ctl:
            unit = Path(tmp) / svc.NAME
            other = Path(tmp) / 'other.service'
            other.write_text('not owned')
            unit.symlink_to(other)
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                svc.install(ROOT, unit)
            ctl.assert_not_called()


if __name__ == '__main__':
    unittest.main()
