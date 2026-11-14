#!/bin/bash
# Main status line (settings.json `statusLine`). Reads the session JSON on stdin
# and prints up to three rows; a segment is left out when its field is absent.
# Fields: https://code.claude.com/docs/en/statusline#available-data
#   1  model, effort, modes, session name, repo/dir, branch, worktree (base,
#      ahead/behind, uncommitted files) or worktree count, PR, lines
#   2  context bar and tokens, cost, wall and API time
#   3  usage limits with reset times, prompt cache, version
# One jq call reads every field; git runs with --no-optional-locks so a refresh
# never takes the index lock an executor's commit needs.
input=$(cat)

eval "$(jq -r '
  def n: if . == null then "" else tostring end;
  @sh "MODEL=\(.model.display_name | n)",
  @sh "EFFORT=\(.effort.level | n)",
  @sh "THINKING=\(.thinking.enabled | n)",
  @sh "FAST=\(.fast_mode | n)",
  @sh "STYLE=\(.output_style.name | n)",
  @sh "VIM=\(.vim.mode | n)",
  @sh "AGENT=\(.agent.name | n)",
  @sh "SESSION=\(.session_name | n)",
  @sh "VERSION=\(.version | n)",
  @sh "DIR=\((.workspace.current_dir // .cwd) | n)",
  @sh "PROJECT=\(.workspace.project_dir | n)",
  @sh "ADDED=\((.workspace.added_dirs // []) | length)",
  @sh "REPO=\(if .workspace.repo then "\(.workspace.repo.owner)/\(.workspace.repo.name)" else "" end)",
  @sh "GIT_WT=\(.workspace.git_worktree | n)",
  @sh "WT_FROM=\(.worktree.original_branch | n)",
  @sh "PR_NUM=\(.pr.number | n)",
  @sh "PR_URL=\(.pr.url | n)",
  @sh "PR_STATE=\(.pr.review_state | n)",
  @sh "PR_KIND=\(.pr.kind | n)",
  @sh "ADD=\(.cost.total_lines_added // 0 | n)",
  @sh "DEL=\(.cost.total_lines_removed // 0 | n)",
  @sh "COST=\(.cost.total_cost_usd // 0 | n)",
  @sh "DUR=\(.cost.total_duration_ms // 0 | floor | n)",
  @sh "API=\(.cost.total_api_duration_ms // 0 | floor | n)",
  @sh "PCT=\(.context_window.used_percentage // 0 | floor | n)",
  @sh "WIN=\(.context_window.context_window_size // 0 | n)",
  @sh "TIN=\(.context_window.total_input_tokens // 0 | n)",
  @sh "TOUT=\(.context_window.total_output_tokens // 0 | n)",
  @sh "BIG=\(.exceeds_200k_tokens | n)",
  @sh "H5=\(.rate_limits.five_hour.used_percentage | if . == null then "" else floor | tostring end)",
  @sh "H5_AT=\(.rate_limits.five_hour.resets_at | n)",
  @sh "D7=\(.rate_limits.seven_day.used_percentage | if . == null then "" else floor | tostring end)",
  @sh "D7_AT=\(.rate_limits.seven_day.resets_at | n)",
  @sh "SPEND=\(.rate_limits.spend_limit.used_percentage | if . == null then "" else floor | tostring end)",
  @sh "SPEND_USD=\(if .rate_limits.spend_limit.used_usd then "$\(.rate_limits.spend_limit.used_usd)/$\(.rate_limits.spend_limit.limit_usd)" else "" end)",
  @sh "C_ON=\(if .prompt_cache then "1" else "" end)",
  @sh "C_WARM=\(.prompt_cache.warm | n)",
  @sh "C_TTL=\(.prompt_cache.ttl | n)",
  @sh "C_EXP=\(.prompt_cache.expires_at | n)",
  @sh "C_HIT=\(.prompt_cache.hit_ratio | if . == null then "" else . * 100 | floor | tostring end)",
  @sh "C_MISS=\(.prompt_cache.misses // 0 | n)",
  @sh "C_CAUSE=\((.prompt_cache.last_miss_cause.causes // []) | join(","))"
' <<<"$input")"

# Colours: 16-colour ANSI, so every terminal theme renders them.
R=$'\033[0m'; B=$'\033[1m'; D=$'\033[2m'
RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLU=$'\033[34m'
MAG=$'\033[35m'; CYN=$'\033[36m'; GRY=$'\033[90m'
SEP=" ${GRY}│${R} "
NOW=$(date +%s)

level() { # percent -> colour
  if [ "${1:-0}" -ge 90 ]; then printf '%s' "$RED"
  elif [ "${1:-0}" -ge 70 ]; then printf '%s' "$YEL"
  else printf '%s' "$GRN"; fi
}
dur() { # seconds -> 3d4h, 2h13m, 5m10s
  local s=${1:-0}; [ "$s" -lt 0 ] && s=0
  if [ "$s" -ge 86400 ]; then printf '%dd%dh' $((s/86400)) $((s%86400/3600))
  elif [ "$s" -ge 3600 ]; then printf '%dh%02dm' $((s/3600)) $((s%3600/60))
  else printf '%dm%02ds' $((s/60)) $((s%60)); fi
}
tok() { # 142000 -> 142k, 1000000 -> 1M
  local t=${1:-0}
  if [ "$t" -ge 1000000 ]; then printf '%sM' "$(LC_NUMERIC=C awk "BEGIN{v=$t/1000000; printf (v==int(v))?\"%d\":\"%.1f\", v}")"
  elif [ "$t" -ge 1000 ]; then printf '%dk' $((t/1000))
  else printf '%d' "$t"; fi
}
link() { # OSC 8 hyperlink: url, text
  printf '\033]8;;%s\a%s\033]8;;\a' "$1" "$2"
}

# ── Row 1: who and where ─────────────────────────────────────────────────
L1="${B}${MAG}◆ ${MODEL}${R}"
[ -n "$EFFORT" ] && L1+=" ${MAG}${EFFORT}${R}"
[ "$THINKING" = "true" ] && L1+=" ${D}think${R}"
[ "$FAST" = "true" ] && L1+=" ${YEL}⚡fast${R}"
[ -n "$STYLE" ] && [ "$STYLE" != "default" ] && L1+=" ${D}${STYLE}${R}"
[ -n "$VIM" ] && L1+=" ${BLU}${VIM}${R}"
[ -n "$AGENT" ] && L1+=" ${CYN}@${AGENT}${R}"
[ -n "$SESSION" ] && L1+="${SEP}${B}${SESSION}${R}"

PLACE="${REPO:-${DIR##*/}}"
[ -n "$REPO" ] && [ "${DIR##*/}" != "${REPO##*/}" ] && PLACE+="${D}/${DIR##*/}${R}"
L1+="${SEP}${BLU}📁 ${PLACE}${R}"
[ -n "$PROJECT" ] && [ "$PROJECT" != "$DIR" ] && L1+=" ${D}from ${PROJECT##*/}${R}"
[ "${ADDED:-0}" -gt 0 ] && L1+=" ${D}+${ADDED} dir${R}"

g() { git --no-optional-locks -C "$DIR" "$@" 2>/dev/null; }
BRANCH=$(g branch --show-current)
[ -n "$BRANCH" ] && L1+="${SEP}${GRN}🌿 ${BRANCH}${R}"
# Worktree: its name, the base it came from, commits ahead/behind that base,
# and uncommitted files. Outside a linked worktree, show how many exist.
if [ -n "$GIT_WT" ]; then
  BASE="$WT_FROM"
  # Any remote's default branch (the remote need not be called origin).
  [ -z "$BASE" ] && BASE=$(g for-each-ref --format='%(symref:short)' 'refs/remotes/*/HEAD' | head -1)
  for c in main master; do
    [ -z "$BASE" ] && g rev-parse --verify -q "$c" >/dev/null && BASE="$c"
  done
  L1+=" ${CYN}🌳 ${GIT_WT}${R}"
  if [ -n "$BASE" ] && AB=$(g rev-list --left-right --count "HEAD...$BASE"); then
    read -r AHEAD BEHIND <<<"$AB"
    L1+=" ${D}← ${BASE}${R}"
    [ "${AHEAD:-0}" -gt 0 ] && L1+=" ${GRN}↑${AHEAD}${R}"
    [ "${BEHIND:-0}" -gt 0 ] && L1+=" ${YEL}↓${BEHIND}${R}"
  fi
  DIRTY=$(g status --porcelain | wc -l)
  [ "${DIRTY:-0}" -gt 0 ] && L1+=" ${YEL}●${DIRTY}${R}"
elif [ -n "$BRANCH" ]; then
  WTS=$(g worktree list --porcelain | grep -c '^worktree ')
  [ "${WTS:-0}" -gt 1 ] && L1+=" ${D}🌳 $((WTS - 1)) worktree$([ "$WTS" -gt 2 ] && echo s)${R}"
fi
if [ -n "$PR_NUM" ]; then
  case "$PR_STATE" in
    approved) PC="$GRN" ;; changes_requested) PC="$RED" ;; draft) PC="$GRY" ;; *) PC="$YEL" ;;
  esac
  [ "$PR_KIND" = "mr" ] && PL="!${PR_NUM}" || PL="#${PR_NUM}"
  [ -n "$PR_URL" ] && PL=$(link "$PR_URL" "$PL")
  L1+=" ${PC}${PL}${PR_STATE:+ ${PR_STATE//_/ }}${R}"
fi
if [ "${ADD:-0}" -gt 0 ] || [ "${DEL:-0}" -gt 0 ]; then
  L1+="${SEP}${GRN}+${ADD}${R} ${RED}-${DEL}${R}"
fi

# ── Row 2: context, cost, time ───────────────────────────────────────────
# 20 cells; each filled cell takes the colour of its own position, so the bar
# shades green -> yellow -> red as it fills.
FILLED=$(( PCT * 20 / 100 )); [ "$FILLED" -gt 20 ] && FILLED=20
BAR=""
for i in $(seq 1 20); do
  if [ "$i" -le "$FILLED" ]; then BAR+="$(level $(( i * 5 )))█"
  else BAR+="${GRY}░"; fi
done
L2="${BAR}${R} $(level "$PCT")${B}${PCT}%${R}"
[ "${WIN:-0}" -gt 0 ] && L2+=" ${D}of $(tok "$WIN")${R}"
[ "${TIN:-0}" -gt 0 ] && L2+=" ${D}in $(tok "$TIN") out $(tok "$TOUT")${R}"
[ "$BIG" = "true" ] && L2+=" ${RED}>200k${R}"
COST_FMT=$(LC_NUMERIC=C printf '$%.2f' "$COST")
L2+="${SEP}${YEL}💰 ${COST_FMT}${R}"
L2+="${SEP}⏱️  $(dur $(( DUR / 1000 )))"
[ "${DUR:-0}" -gt 0 ] && [ "${API:-0}" -gt 0 ] && L2+=" ${D}api $(( API * 100 / DUR ))%${R}"

# ── Row 3: limits and cache (only once the first response is in) ────────
L3=""
add3() { [ -n "$L3" ] && L3+="$SEP"; L3+="$1"; }
if [ -n "$H5" ] || [ -n "$D7" ]; then
  S="⏳"
  [ -n "$H5" ] && S+=" 5h $(level "$H5")${H5}%${R}" && [ -n "$H5_AT" ] && S+=" ${D}↻$(dur $(( H5_AT - NOW )))${R}"
  [ -n "$D7" ] && S+=" 7d $(level "$D7")${D7}%${R}" && [ -n "$D7_AT" ] && S+=" ${D}↻$(dur $(( D7_AT - NOW )))${R}"
  add3 "$S"
fi
[ -n "$SPEND" ] && add3 "💳 $(level "$SPEND")${SPEND}%${R}${SPEND_USD:+ ${D}${SPEND_USD}${R}}"
if [ -n "$C_ON" ]; then
  if [ "$C_WARM" = "true" ]; then S="${CYN}🗄️  warm${R}"; else S="${BLU}🗄️  cold${R}"; fi
  [ -n "$C_TTL" ] && S+=" ${D}${C_TTL}${R}"
  [ "$C_WARM" = "true" ] && [ -n "$C_EXP" ] && S+=" ${D}⌛$(dur $(( C_EXP - NOW )))${R}"
  [ -n "$C_HIT" ] && S+=" hit $( [ "$C_HIT" -ge 80 ] && printf '%s' "$GRN" || printf '%s' "$YEL")${C_HIT}%${R}"
  [ "${C_MISS:-0}" -gt 0 ] && S+=" ${YEL}miss ${C_MISS}${R}${C_CAUSE:+ ${D}(${C_CAUSE})${R}}"
  add3 "$S"
fi
[ -n "$VERSION" ] && add3 "${D}v${VERSION}${R}"

printf '%s\n' "$L1" "$L2"
[ -n "$L3" ] && printf '%s\n' "$L3"
exit 0
