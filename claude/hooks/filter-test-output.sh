#!/usr/bin/env bash
# PostToolUse hook (matcher: Bash). Shortens the output of a long, passing test
# run to its summary, so a green suite does not fill the context (ADR 0123).
# Claude Code only: Codex has no way to replace a tool's output.
#
# A passing suite prints hundreds of progress lines and a short summary at the
# end. The agent needs the summary. So, when a test runner sits at command
# position and its output passes LIMIT lines, the hook replaces each stream with:
#
#   - one line that says how many lines it hid and how to see them all,
#   - up to WARN_MAX hidden lines that name a warning, deprecation, skip or
#     risky test,
#   - the last KEEP lines, which hold the runner's summary.
#
# Runners: artisan test, phpunit, paratest, pest, vitest, jest, npm/pnpm/yarn/bun
# test, pytest. The command-position rule matches require-isolated-test-runner.sh.
#
# A failing run is never shortened. PostToolUse fires only after a tool
# succeeds, but the docs do not say a non-zero exit counts as a failure. So
# the hook also leaves the output alone when it shows a failure marker.
#
# The hook also leaves output alone when:
#   - the command already pipes or redirects its output (`| cat` shows it all),
#   - the run was interrupted,
#   - jq fails or the input is not what it expects (fail open: the full output
#     stays, which costs tokens and nothing else).
set -uo pipefail

LIMIT=150
KEEP=40
WARN_MAX=20

input="$(cat)"
command -v jq >/dev/null || exit 0
command="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
[ -n "$command" ] || exit 0
[ "$(printf '%s' "$input" | jq -r '.tool_response.interrupted // false' 2>/dev/null)" = false ] || exit 0

assign='[A-Za-z_][A-Za-z0-9_]*=("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:]]*)[[:space:]]+'
sep="(^|[;&|(])[[:space:]]*(env[[:space:]]+)?($assign)*"
php="([A-Za-z0-9_./-]*/)?php[0-9.]*[[:space:]]+"
end='([[:space:];&|<>)]|$)'
path='(\.?/)?([A-Za-z0-9_./-]*/)?'
artisan="${sep}($php([^;&|()]*[[:space:]]+)?)?\.?/?artisan[[:space:]]+test${end}"
phpbin="${sep}($php)?${path}(phpunit|paratest|pest)${end}"
jsbin="${sep}((npx|bunx|pnpm[[:space:]]+exec|yarn)[[:space:]]+)?${path}(vitest|jest)${end}"
script="${sep}(npm|pnpm|yarn|bun)[[:space:]]+(run[[:space:]]+)?test${end}"
pytest="${sep}((python[0-9.]*|uv[[:space:]]+run|poetry[[:space:]]+run)[[:space:]]+(-m[[:space:]]+)?)?${path}pytest${end}"
printf '%s' "$command" | grep -Eq "$artisan|$phpbin|$jsbin|$script|$pytest" || exit 0

# `||` is not a pipe, and `2>&1` only merges the streams.
plain="$(printf '%s' "$command" | sed -E 's/\|\|//g; s/[0-9]?>&[0-9]//g')"
case "$plain" in *'|'*|*'>'*) exit 0 ;; esac

ansi=$'s/\x1b\\[[0-9;?]*[A-Za-z]//g'
fail='^[[:space:]]*(FAIL|FAILED|FAILURES!|ERRORS!)([[:space:]]|$)|[1-9][0-9]* (failed|failures?|errors?)([^A-Za-z]|$)|^Traceback '

shorten() {   # shorten STREAM: print the shortened stream, or fail when it stays
  local text total hidden
  text="$(printf '%s' "$input" | jq -r --arg s "$1" '.tool_response[$s] // empty' | sed -E "$ansi")"
  total="$(printf '%s\n' "$text" | wc -l)"
  [ "$total" -gt "$LIMIT" ] || return 1
  hidden=$((total - KEEP))
  printf '[filter-test-output] Passing run: %d of %d lines hidden. Rerun with `| cat` to see them all.\n' "$hidden" "$total"
  printf '%s\n' "$text" | head -n "$hidden" \
    | grep -Ei 'warn|deprecat|skipped|risky|incomplete' | head -n "$WARN_MAX"
  printf '%s\n' "$text" | tail -n "$KEEP"
}

all="$(printf '%s' "$input" | jq -r '(.tool_response.stdout // "") + "\n" + (.tool_response.stderr // "")' | sed -E "$ansi")"
printf '%s\n' "$all" | grep -Eq "$fail" && exit 0

out="$(shorten stdout)" && changed=1 || out="$(printf '%s' "$input" | jq -r '.tool_response.stdout // ""')"
err="$(shorten stderr)" && changed=1 || err="$(printf '%s' "$input" | jq -r '.tool_response.stderr // ""')"
[ "${changed:-0}" = 1 ] || exit 0

printf '%s' "$input" | jq -c --arg o "$out" --arg e "$err" \
  '{hookSpecificOutput: {hookEventName: "PostToolUse",
    updatedToolOutput: (.tool_response + {stdout: $o, stderr: $e})}}' 2>/dev/null || exit 0
