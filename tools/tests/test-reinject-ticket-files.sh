#!/usr/bin/env bash
# Fixture tests for claude/hooks/reinject-ticket-files.sh (SessionStart, compact).
# Run: tools/tests/test-reinject-ticket-files.sh
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../claude/hooks" && pwd)/reinject-ticket-files.sh"
command -v jq >/dev/null || { echo "test-reinject: jq is required" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git init -q -b worktree-LD-7 "$TMP/ticket"
mkdir -p "$TMP/ticket/docs/tasks" "$TMP/ticket/src"
touch "$TMP/ticket/docs/tasks/LD-7-open.md" "$TMP/ticket/docs/tasks/LD-7-plan.md"
git init -q -b main "$TMP/main"
git init -q -b feature/LD-8 "$TMP/nofiles"

PASS=0; FAIL=0
run() { jq -n --arg c "$1" '{cwd:$c,source:"compact",hook_event_name:"SessionStart"}' | bash "$HOOK"; }
check() { # label, expected-substring-or-EMPTY, actual
  if { [ "$2" = EMPTY ] && [ -z "$3" ]; } || { [ "$2" != EMPTY ] && [[ "$3" == *"$2"* ]]; }; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1)); echo "FAIL [$1]: expected '$2', got '$3'"
  fi
}

check ticket-files   "Ticket LD-7 keeps its state in: docs/tasks/LD-7-open.md, docs/tasks/LD-7-plan.md." "$(run "$TMP/ticket")"
check from-subdir    "docs/tasks/LD-7-open.md" "$(run "$TMP/ticket/src")"
check no-todo-listed EMPTY "$(run "$TMP/ticket" | grep -o 'LD-7-todo')"
check no-ticket      EMPTY "$(run "$TMP/main")"
check no-files       EMPTY "$(run "$TMP/nofiles")"
check missing-dir    EMPTY "$(run /nonexistent)"
check no-cwd         EMPTY "$(echo '{}' | bash "$HOOK")"
check bad-json       EMPTY "$(echo 'not json' | bash "$HOOK")"
echo 'not json' | bash "$HOOK" >/dev/null; check exit-zero 0 "$?"

echo "reinject-ticket-files: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
