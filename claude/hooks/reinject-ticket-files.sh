#!/usr/bin/env bash
# SessionStart hook (matcher: compact). After a compaction, names the ticket's
# working files so the session re-reads its open work instead of searching for
# it. The ticket key comes from the branch (`LD-514`, `worktree-LD-514`); the
# files are the ones `/plan` and `/build` keep: docs/tasks/<TICKET>-plan.md,
# -todo.md and -open.md (AGENTS.md §Session and context).
#
# SessionStart cannot block; plain stdout becomes context. Silent when the
# branch names no ticket or no file exists. Exit 0 always.
set -uo pipefail

command -v jq >/dev/null || exit 0
cwd="$(jq -r '.cwd // empty' 2>/dev/null)" || exit 0
[ -n "$cwd" ] && [ -d "$cwd" ] || exit 0

root="$(git --no-optional-locks -C "$cwd" rev-parse --show-toplevel 2>/dev/null)" || exit 0
branch="$(git --no-optional-locks -C "$cwd" branch --show-current 2>/dev/null)"
ticket="$(grep -oE '[A-Z][A-Z0-9]+-[0-9]+' <<<"$branch" | head -1)"
[ -n "$ticket" ] || exit 0

files=()
for kind in open todo plan; do
  f="docs/tasks/$ticket-$kind.md"
  [ -f "$root/$f" ] && files+=("$f")
done
[ "${#files[@]}" -gt 0 ] || exit 0

printf 'Context was compacted. Ticket %s keeps its state in: %s.\n' "$ticket" "$(IFS=,; echo "${files[*]}" | sed 's/,/, /g')"
printf 'Re-read the open items there before you continue; do not rely on the summary alone.\n'
exit 0
