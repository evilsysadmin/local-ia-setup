#!/usr/bin/env python3
"""Disposable local coding benchmark for the Bonsai/OpenCode agent."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CODE = '''def median(numbers):
    """Return the median of numbers; raise ValueError for empty input."""
    if not numbers:
        raise ValueError("Empty sample")
    ordered = sorted(numbers)
    return ordered[len(ordered) // 2]
'''
TESTS = '''import unittest
from stats import median


class MedianTests(unittest.TestCase):
    def test_odd(self):
        self.assertEqual(median([5, 1, 3]), 3)

    def test_even(self):
        self.assertEqual(median([1, 2, 3, 4]), 2.5)

    def test_negative(self):
        self.assertEqual(median([-8, -2]), -5)

    def test_does_not_mutate(self):
        values = [3, 1, 2]
        median(values)
        self.assertEqual(values, [3, 1, 2])

    def test_empty(self):
        with self.assertRaises(ValueError):
            median([])


if __name__ == "__main__":
    unittest.main()
'''
AGENTS = '''# Bonsai Arena — mini coding task

- Identify and fix the bug in stats.py using the included unittest tests.
- Modify only stats.py; do not change test_stats.py or AGENTS.md.
- Execute python3 -m unittest -v and report the actual result. Do not commit.
- Never use the network, install packages, or edit files outside this arena.
'''
IGNORE = "__pycache__/\n*.py[cod]\n"


def command(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=root, text=True, capture_output=True, check=False, timeout=30)


def create_arena(parent: Path | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="bonsai-arena-", dir=parent)).resolve()
    for path, content in {"stats.py": CODE, "test_stats.py": TESTS,
                          "AGENTS.md": AGENTS, ".gitignore": IGNORE}.items():
        (root / path).write_text(content, encoding="utf-8")
    for args in [
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.name", "Bonsai Arena"),
        ("git", "config", "user.email", "bonsai-arena@invalid.example"),
        ("git", "add", "stats.py", "test_stats.py", "AGENTS.md", ".gitignore"),
        ("git", "commit", "-qm", "chore: initial failing puzzle"),
        ("git", "switch", "-qc", "bonsai/arena"),
    ]:
        result = command(root, *args)
        if result.returncode:
            raise RuntimeError(f"Could not prepare arena: {args[:2]} ({result.stderr.strip()})")
    baseline = command(root, sys.executable, "-B", "-m", "unittest", "-v")
    if baseline.returncode == 0 or "FAILED" not in baseline.stderr:
        raise RuntimeError("The arena fixture did not fail its expected tests")
    return root


def assess(root: Path) -> bool:
    root = root.resolve(strict=True)
    if not root.is_dir() or not (root / "stats.py").is_file() or not (root / "AGENTS.md").is_file():
        raise ValueError("Invalid arena directory")
    if not (root / "AGENTS.md").read_text(encoding="utf-8").startswith("# Bonsai Arena"):
        raise ValueError("Not a Bonsai Arena directory")
    protected = {"test_stats.py": TESTS, "AGENTS.md": AGENTS, ".gitignore": IGNORE}
    if any(not (root / file).is_file() or (root / file).read_text(encoding="utf-8") != content
           for file, content in protected.items()):
        print("FAIL: protected test/rules fixture changed")
        return False
    expected = {"stats.py", "test_stats.py", "AGENTS.md", ".gitignore"}
    tracked = command(root, "git", "ls-files", "--cached").stdout.splitlines()
    if set(tracked) != expected:
        print("FAIL: unexpected tracked files")
        return False
    if (root / "stats.py").read_text(encoding="utf-8") == CODE:
        print("FAIL: stats.py has not changed")
        return False
    status = command(root, "git", "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    if any(line[3:] != "stats.py" for line in status):
        print("FAIL: unexpected changes outside stats.py")
        return False
    if command(root, "git", "diff", "--check").returncode:
        print("FAIL: whitespace errors")
        return False
    result = command(root, sys.executable, "-B", "-m", "unittest", "-v")
    print(result.stdout + result.stderr)
    if result.returncode:
        print("FAIL: unittest suite is not green")
        return False
    print("PASS: five tests green and only stats.py changed")
    return True


def main(argv: list[str]) -> None:
    if argv == ["create"]:
        root = create_arena()
        print(f"ARENA={root}")
        print("The baseline suite FAILS intentionally.")
        print("From the local-ia-setup checkout, launch the verified local agent:")
        print(f"  PROJECT={root} make agent-build")
        print("Prompt: Lee AGENTS.md, corrige stats.py y pasa todos los tests.")
        print("After completing the task, evaluate:")
        print(f"  PROJECT={root} make arena-check")
    elif argv == ["check"]:
        raw = os.environ.get("PROJECT")
        if not raw:
            raise ValueError("Set PROJECT=/tmp/bonsai-arena-... to check the challenge")
        if not assess(Path(raw)):
            sys.exit(1)
    else:
        raise ValueError("Usage: arena.py {create|check}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
