"""No-GPU tests for disposable coding arena, fixture integrity and score."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import arena


class ArenaTests(unittest.TestCase):
    def test_fixture_intentionally_fails_on_clean_feature_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = arena.create_arena(Path(tmp))
            branch = arena.command(root, "git", "branch", "--show-current")
            self.assertEqual(branch.stdout.strip(), "bonsai/arena")
            self.assertFalse(arena.command(root, "git", "status", "--porcelain").stdout.strip())
            run = arena.command(root, sys.executable, "-B", "-m", "unittest", "-v")
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("FAILED", run.stderr)
            self.assertFalse(arena.assess(root))

    def test_correct_fix_passes_with_unchanged_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = arena.create_arena(Path(tmp))
            (root / "stats.py").write_text(
                'def median(numbers):\n'
                '    if not numbers:\n        raise ValueError("Empty sample")\n'
                '    ordered = sorted(numbers)\n    mid = len(ordered) // 2\n'
                '    if len(ordered) % 2:\n        return ordered[mid]\n'
                '    return (ordered[mid - 1] + ordered[mid]) / 2\n'
            )
            self.assertTrue(arena.assess(root))

    def test_tampering_with_tests_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = arena.create_arena(Path(tmp))
            (root / "test_stats.py").write_text("# tests deleted\n")
            self.assertFalse(arena.assess(root))

    def test_unexpected_untracked_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = arena.create_arena(Path(tmp))
            (root / "stats.py").write_text("def median(numbers): return 2\n")
            (root / "extra.sh").write_text("echo hello\n")
            self.assertFalse(arena.assess(root))

    def test_unrelated_directory_is_not_arena(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                arena.assess(Path(tmp))


if __name__ == "__main__":
    unittest.main()
