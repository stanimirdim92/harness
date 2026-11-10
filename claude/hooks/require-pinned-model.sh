#!/usr/bin/env bash
# PreToolUse hook (Agent|Task). Since v2.1.251 a per-call `model` beats the
# persona's frontmatter pin. Allow a per-call model only when it is a strictly
# higher tier than the pin (haiku < sonnet < opus < fable). Calls without a
# model, and agents with no file in ../agents, pass. Fails closed without jq
# (docs/adr/0087). See docs/adr/0125.
set -uo pipefail

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}' 2>/dev/null \
    || printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Cannot verify the agent model override."}}'
  exit 0
}

command -v jq >/dev/null || deny "Cannot verify the agent model override: jq is missing."
input="$(cat 2>/dev/null)"
fields="$(jq -er '
  (.tool_input // {}) as $t |
  [($t.subagent_type // $t.agent_type // ""), ($t.model // "")] |
  if all(.[]; type == "string" and test("^[A-Za-z0-9._:\\[\\]-]*$")) then join(" ") else error("bad") end
' <<<"$input" 2>/dev/null)" || deny "Cannot verify the agent model override: invalid dispatch input."
agent="${fields%% *}"
requested="${fields#* }"
[ -n "$requested" ] || exit 0

file="$(dirname "$0")/../agents/$agent.md"
[ -n "$agent" ] && [ -f "$file" ] || exit 0
pinned="$(awk '/^---$/{c++; next} c==1 && /^model:/{sub(/^model:[ \t]*/, ""); print; exit}' "$file")"
[ -n "$pinned" ] || exit 0

tier() {
  case "$1" in
    *haiku*) echo 1 ;; *sonnet*) echo 2 ;; *opus*) echo 3 ;; *fable*) echo 4 ;; *) echo 0 ;;
  esac
}
want="$(tier "$requested")"
have="$(tier "$pinned")"
[ "$want" -gt 0 ] && [ "$have" -gt 0 ] && [ "$want" -gt "$have" ] && exit 0
deny "$agent is pinned to $pinned. A per-call model may only raise the tier (CLAUDE.md, Models). Drop the model parameter."
