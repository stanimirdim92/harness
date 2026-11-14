#!/usr/bin/env bash
# Fixture tests for claude/hooks/log-failure-event.sh (StopFailure, PermissionDenied).
# Run: tools/tests/test-log-failure-event.sh
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../claude/hooks" && pwd)/log-failure-event.sh"
command -v jq >/dev/null || { echo "test-log-failure: jq is required" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export HARNESS_FAILURE_LOG="$TMP/logs/failures.jsonl"

PASS=0; FAIL=0
check() { # label, expected, actual
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL [$1]: expected '$2', got '$3'"; fi
}

out="$(jq -n '{hook_event_name:"StopFailure",session_id:"s1",cwd:"/r",error:"rate_limit",error_details:"429 Too Many Requests"}' | bash "$HOOK")"
check stop-silent "" "$out"
check stop-error rate_limit "$(jq -r 'select(.event=="StopFailure") | .error' "$HARNESS_FAILURE_LOG")"
check stop-details "429 Too Many Requests" "$(jq -r 'select(.event=="StopFailure") | .details' "$HARNESS_FAILURE_LOG")"

jq -n '{hook_event_name:"PermissionDenied",session_id:"s2",cwd:"/r",permission_mode:"auto",tool_name:"Bash",tool_input:{command:"curl -H \"Authorization: Bearer SECRET123\" x"},reason:"[Irreversible Local Destruction]"}' | bash "$HOOK"
check denied-tool Bash "$(jq -r 'select(.event=="PermissionDenied") | .tool' "$HARNESS_FAILURE_LOG")"
check denied-reason "[Irreversible Local Destruction]" "$(jq -r 'select(.event=="PermissionDenied") | .reason' "$HARNESS_FAILURE_LOG")"
check no-tool-input 0 "$(grep -c 'SECRET123' "$HARNESS_FAILURE_LOG")"

long="$(printf 'x%.0s' $(seq 1 1000))"
jq -n --arg d "$long" '{hook_event_name:"StopFailure",error:"server_error",error_details:$d}' | bash "$HOOK"
check details-capped 300 "$(jq -r 'select(.error=="server_error") | .details | length' "$HARNESS_FAILURE_LOG")"

check one-line-each 3 "$(wc -l <"$HARNESS_FAILURE_LOG" | tr -d ' ')"
echo 'not json' | bash "$HOOK"; check bad-json-exit 0 "$?"

echo "log-failure-event: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
