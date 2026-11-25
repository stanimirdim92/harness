#!/usr/bin/env bash
# Fixture tests for claude/hooks/eval-todo-hint.sh, the SessionStart line that
# says how many shipped tickets and bugs skipped their eval step.
#
# The hook finds eval.py from its own real path, so each case copies the hook
# into a throwaway harness tree (claude/hooks/ and tools/evals/) and puts a
# stub eval.py in it. The stub plays one outcome: a count, zero, a failure,
# garbage, or a hang. The silent cases carry the weight: a hint that fires when
# nothing is wrong, or a session that waits on it, gets the hook deleted.
#
# Run: tools/tests/test-eval-todo-hint.sh
set -uo pipefail

HOOK_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../claude/hooks" && pwd)/eval-todo-hint.sh"
command -v jq >/dev/null || { echo "test-eval-todo-hint: jq is required" >&2; exit 1; }
[ -f "$HOOK_SRC" ] || { echo "test-eval-todo-hint: $HOOK_SRC is missing" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0; FAILED=()

mkdir -p "$TMP/harness/claude/hooks" "$TMP/harness/tools/evals" "$TMP/project/sub"
cp "$HOOK_SRC" "$TMP/harness/claude/hooks/eval-todo-hint.sh"
HOOK="$TMP/harness/claude/hooks/eval-todo-hint.sh"
STUB="$TMP/harness/tools/evals/eval.py"
git -C "$TMP/project" init -q
PROJECT="$(cd "$TMP/project" && pwd -P)"

stub() { printf '%s\n' "$1" > "$STUB"; }

check() { # name, expected, actual
  if [ "$2" = "$3" ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); FAILED+=("$1: expected [$2], got [$3]"); fi
}

run_hook() { # extra args; stdin is the session JSON with cwd = $CWD_JSON
  printf '{"cwd":"%s"}' "${CWD_JSON:-$TMP/project}" | bash "$HOOK" "$@" 2>"$TMP/stderr"
}

LINE='evals: 2 tickets without recall, 1 bugs without a case — run eval.py todo'

# 1. items pending: the one line
stub 'print("2 1")'
out="$(run_hook)"; code=$?
check 'pending: line' "$LINE" "$out"
check 'pending: exit 0' 0 "$code"

# 2. only bugs pending still prints, with the zero spelled out
stub 'print("0 3")'
out="$(run_hook)"
check 'bugs only' 'evals: 0 tickets without recall, 3 bugs without a case — run eval.py todo' "$out"

# 3. zero is silent
stub 'print("0 0")'
out="$(run_hook)"; code=$?
check 'zero: silent' '' "$out"
check 'zero: exit 0' 0 "$code"

# 4. a failing eval.py is silent, even when it printed a count first
stub 'print("2 1"); raise SystemExit(1)'
out="$(run_hook)"; code=$?
check 'failure: silent' '' "$out"
check 'failure: exit 0' 0 "$code"

# 5. output that is not a count is silent
stub 'print("Traceback: boom")'
out="$(run_hook)"; code=$?
check 'garbage: silent' '' "$out"
check 'garbage: exit 0' 0 "$code"

# 6. a hang is cut off at 2 seconds, silently
stub 'import time; time.sleep(30); print("2 1")'
start=$SECONDS
out="$(run_hook)"; code=$?
elapsed=$((SECONDS - start))
check 'timeout: silent' '' "$out"
check 'timeout: exit 0' 0 "$code"
check 'timeout: under 4 seconds' 1 "$([ "$elapsed" -lt 4 ] && echo 1 || echo 0)"

# 7. the hook runs `eval.py todo --count` from the project's top directory,
#    even when the session starts in a subdirectory
stub "import os, sys; open('$TMP/seen', 'w').write(' '.join(sys.argv[1:]) + '|' + os.getcwd()); print('1 0')"
CWD_JSON="$TMP/project/sub" run_hook >/dev/null
check 'call: arguments and top directory' "todo --count|$PROJECT" "$(cat "$TMP/seen" 2>/dev/null)"

# 8. a session directory that is not a git checkout still runs the count there
mkdir -p "$TMP/plain"
CWD_JSON="$TMP/plain" run_hook >/dev/null
check 'call: no git checkout' "todo --count|$(cd "$TMP/plain" && pwd -P)" "$(cat "$TMP/seen" 2>/dev/null)"

# 9. a symlink to the hook (the installed layout) still finds the harness
mkdir -p "$TMP/home/.claude/hooks"
ln -s "$HOOK" "$TMP/home/.claude/hooks/eval-todo-hint.sh"
stub 'print("2 1")'
out="$(printf '{"cwd":"%s"}' "$TMP/project" | bash "$TMP/home/.claude/hooks/eval-todo-hint.sh")"
check 'symlink: line' "$LINE" "$out"

# 10. no JSON on stdin at all: still exits 0
out="$(bash "$HOOK" </dev/null 2>/dev/null)"; code=$?
check 'no input: exit 0' 0 "$code"

# 11. --report wraps the line for the user and the model; zero stays silent
stub 'print("2 1")'
out="$(run_hook --report)"
check 'report: systemMessage' "$LINE" "$(jq -r '.systemMessage' <<<"$out" 2>/dev/null)"
check 'report: additionalContext' "$LINE" "$(jq -r '.hookSpecificOutput.additionalContext' <<<"$out" 2>/dev/null)"
check 'report: event name' SessionStart "$(jq -r '.hookSpecificOutput.hookEventName' <<<"$out" 2>/dev/null)"
stub 'print("0 0")'
out="$(run_hook --report)"; code=$?
check 'report zero: silent' '' "$out"
check 'report zero: exit 0' 0 "$code"

# 12. the hook is registered last under startup|resume, after the other session-start hook there
settings="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../claude" && pwd)/settings.json"
commands="$(jq -r '[.hooks.SessionStart[] | select(.matcher == "startup|resume") | .hooks[].command]' "$settings" 2>/dev/null)"
check 'settings: last under startup|resume' '$HOME/.claude/hooks/eval-todo-hint.sh --report' "$(jq -r 'last' <<<"$commands" 2>/dev/null)"
check 'settings: not the only one there' 1 "$(jq 'length > 1 | if . then 1 else 0 end' <<<"$commands" 2>/dev/null)"

if [ "$FAIL" -gt 0 ]; then
  printf 'test-eval-todo-hint: %s passed, %s FAILED\n' "$PASS" "$FAIL" >&2
  printf '  %s\n' "${FAILED[@]}" >&2
  exit 1
fi
printf 'test-eval-todo-hint: %s passed\n' "$PASS"
