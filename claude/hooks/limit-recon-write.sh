#!/usr/bin/env bash
# PreToolUse hook (matcher: Write), scoped to repo-recon via its frontmatter
# `hooks:`. Recon is read-only except for one file: its own report, written to
# docs/specs/[TICKET]-recon-[area].md so the full hit list stays out of the
# caller's context. Any other path is denied. Exit 0 always; the decision is
# JSON on stdout, per https://code.claude.com/docs/en/hooks. See docs/adr/0127.
set -euo pipefail

command -v jq >/dev/null || {
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"limit-recon-write.sh needs jq to check this path. Install jq, then retry."}}'
  exit 0
}

path="$(jq -r '.tool_input.file_path // empty' 2>/dev/null)" || path=""

dir="${path%/*}"
base="${path##*/}"
case "$path" in
  *..*) ;;
  *)
    case "$dir" in
      docs/specs | */docs/specs)
        case "$base" in *-recon-*.md) exit 0 ;; esac
        ;;
    esac
    ;;
esac

jq -n --arg p "$path" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: ("repo-recon may write only its report, docs/specs/[TICKET]-recon-[area].md. Denied: " + $p)
  }
}'
exit 0
