#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

hooks_path=$(git config --get core.hooksPath || true)
# A relative or absolute path to this checkout's .githooks is the same setting.
if [[ -n "$hooks_path" && "$(realpath -m -- "$hooks_path")" != "$(realpath -m -- .githooks)" ]]; then
    echo "Existing core.hooksPath=$hooks_path; reconcile it before installing .githooks." >&2
    exit 1
fi
test -x vendor/bin/pint || { echo 'Run bin/worktree-setup.sh first.' >&2; exit 1; }
command -v yarn >/dev/null || { echo 'Install the project Node/Corepack runtime first.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Install python3 first.' >&2; exit 1; }
python3 bin/pre-commit.py --setup
git config --local core.hooksPath .githooks
echo 'Quality hooks ready. Run python3 bin/pre-commit.py run --files FILE for a focused check.'
