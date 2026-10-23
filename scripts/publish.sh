#!/usr/bin/env bash
# One-time publishing helper; explicitly invoked by the repository owner.
set -euo pipefail
cd "$(dirname "$0")/.."
visibility="${VISIBILITY:-private}"
[[ "$visibility" == private || "$visibility" == public ]] || { echo 'VISIBILITY must be private or public' >&2; exit 2; }
command -v gh >/dev/null || { echo 'Install and log in with GitHub CLI (gh auth login).' >&2; exit 1; }
gh auth status >/dev/null
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  [[ "$(git rev-parse --show-toplevel)" == "$PWD" ]] || { echo 'Nested in another git worktree. Move to a standalone directory.' >&2; exit 1; }
else
  git init -b main
fi
# Stage only explicit version-controlled source files; never blindly stage everything.
git add README.md Makefile LICENSE AGENTS.md .gitignore .env.example scripts/local-ia scripts/local_setup.py scripts/publish.sh tests/test_local_setup.py .github/workflows/ci.yml
if ! git diff --cached --quiet; then
  git commit -m 'feat: reproducible local Bonsai CUDA and OpenCode V2 setup'
fi
if git remote get-url origin >/dev/null 2>&1; then
  echo "Already has remote origin: $(git remote get-url origin)" >&2
  exit 1
fi
# Avoid overwriting an existing repository. Requires user authentication.
if gh repo view evilsysadmin/local-ia-setup >/dev/null 2>&1; then
  echo 'Repository already exists; inspect manually before adding remote/pushing.' >&2
  exit 1
fi
gh repo create evilsysadmin/local-ia-setup "--$visibility" --source=. --remote=origin --push
