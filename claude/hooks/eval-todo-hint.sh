#!/usr/bin/env bash
# SessionStart hook (matcher: startup|resume). Says how many shipped tickets and bugs skipped their eval step.
#
# `eval.py todo` lists the tickets that shipped without a Plan recall row and
# the Shipped bugs rows without an eval case. /release prompts for both steps,
# but the owner sometimes skips /release, so this line asks again at the start
# of a session. It prints nothing when the count is zero.
#
# The hook finds eval.py from its own real path, so it works through the
# symlink in ~/.claude/hooks. `timeout 2` keeps the session from waiting on
# git or on a slow disk. Any failure prints nothing. SessionStart cannot
# block, and a session must never fail to start because this hook had a bad
# day, so it exits 0 always.
set -uo pipefail

if [ "${1:-}" = --report ]; then
  output="$(bash "${BASH_SOURCE[0]}")"
  [ -n "$output" ] || exit 0
  jq -n --arg message "$output" '{systemMessage:$message,hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$message}}'
  exit 0
fi

input=""
[ -t 0 ] || input="$(cat 2>/dev/null)"
cwd="$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)"
[ -n "$cwd" ] && [ -d "$cwd" ] && cd "$cwd" 2>/dev/null
top="$(git rev-parse --show-toplevel 2>/dev/null)" && cd "$top" 2>/dev/null

script="$(realpath "${BASH_SOURCE[0]}" 2>/dev/null)" || exit 0
root="$(cd "$(dirname "$script")/../.." 2>/dev/null && pwd -P)" || exit 0
counts="$(timeout 2 python3 "$root/tools/evals/eval.py" todo --count 2>/dev/null)" || exit 0

if [[ "$counts" =~ ^([0-9]+)\ ([0-9]+)$ ]]; then
  tickets="${BASH_REMATCH[1]}"
  bugs="${BASH_REMATCH[2]}"
  if [ $((10#$tickets + 10#$bugs)) -gt 0 ]; then
    printf 'evals: %s tickets without recall, %s bugs without a case — run eval.py todo\n' "$tickets" "$bugs"
  fi
fi
exit 0
