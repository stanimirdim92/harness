#!/usr/bin/env bash
# StopFailure and PermissionDenied hook (no matcher). Appends one JSON line per
# event to ~/.claude/logs/failures.jsonl, so a run that ended on an API error
# or an auto-mode denial leaves its cause on disk, not only in a closed
# terminal. Neither event can block; output and exit code are ignored.
#
# Logged: time, event, session, cwd, and the cause -- `error` and
# `error_details` for StopFailure; `tool_name` and `reason` for
# PermissionDenied. `tool_input` is never logged: a command can carry a secret.
set -uo pipefail

command -v jq >/dev/null || exit 0
log="${HARNESS_FAILURE_LOG:-$HOME/.claude/logs/failures.jsonl}"
mkdir -p "$(dirname "$log")" 2>/dev/null || exit 0

jq -c '
  def cut: if type == "string" then .[0:300] else . end;
  {
    time: (now | todate),
    event: .hook_event_name,
    session: .session_id,
    cwd: .cwd
  }
  + (if .hook_event_name == "StopFailure"
     then {error: .error, details: (.error_details | cut)}
     else {tool: .tool_name, reason: (.reason | cut), mode: .permission_mode}
     end)
' >>"$log" 2>/dev/null
exit 0
