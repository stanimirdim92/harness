#!/usr/bin/env bash
# One-time-per-machine MCP server setup for Claude Code.
#
# This is deliberately a SCRIPT, not a synced JSON file: `claude mcp add`
# writes into ~/.claude.json (user scope), which also holds per-project
# trust state and can carry OAuth tokens/API keys. Syncing that whole file
# across machines would leak/overwrite machine-specific state, so it's
# excluded in README.md's "Deliberately not synced" list. Run this script
# by hand on each machine instead:
#
#   ./claude/mcp/setup.sh
#
# No secrets are passed to this script. Auth headers are written as literal
# `${VAR}` placeholders that Claude Code expands from the environment when it
# loads the server, so the stored config holds a variable name, not a token
# (see https://code.claude.com/docs/en/mcp). Export the variables the servers
# below name in the shell that starts Claude Code — e.g. from ~/.bashrc or a
# secret manager — not here.
#
# Re-running is safe: each server is skipped if it already exists. `claude mcp
# add` fails with a non-zero exit on a duplicate name, and with `set -e` that
# would abort the script before the later servers were ever added, so the
# check has to happen before the add rather than being left to the failure.
set -euo pipefail

# Adds one server unless a server of that name already resolves. `claude mcp
# get` also resolves project- and local-scope servers, so an existing
# same-named server at another scope is reported and skipped rather than
# silently shadowed by a new user-scope entry.
add_server() {
  local name="$1"
  shift

  if claude mcp get "$name" >/dev/null 2>&1; then
    echo "    skipped: '$name' already exists (re-add with: claude mcp remove $name --scope user)"
    return 0
  fi

  claude mcp add "$name" "$@"
}

# GitHub: no MCP server. The `gh` CLI covers GitHub work.
#
# Apify: not user-wide. Only the leadbuster project uses it, so add it there
# at local scope, from that project's root:
#
#   claude mcp add apify --transport http https://mcp.apify.com/ \
#     --header 'Authorization: Bearer ${APIFY_TOKEN}' --scope local

# Deliberately NOT configured: @modelcontextprotocol/server-filesystem.
# It was previously added at user scope rooted at "$HOME", which reached
# around settings.json's Read-deny paths (~/.ssh, ~/.aws, ~/.config/gh,
# ~/.git-credentials) — the deny list constrains Claude Code's own file
# tools, not an MCP server's. The built-in Read/Write/Glob/Grep tools
# already cover the workspace, so the server's only real addition was reach
# outside it. On a machine that already has it, remove it:
#
#   claude mcp remove filesystem --scope user
#
# If a future task genuinely needs MCP filesystem access, add it per-project
# with an explicit narrow root and a pinned version, not user-wide.

# Atlassian (Jira/Confluence) is not added here: it comes from the claude.ai
# "Atlassian MCP" connector (Settings → Connectors on claude.ai), which Claude
# Code loads as `mcp__claude_ai_Atlassian_MCP__*`.

echo "==> Figma design-to-code skill"
# The Figma MCP server is not added here: it comes from the claude.ai "Figma"
# connector (Settings → Connectors on claude.ai), which Claude Code loads as
# `mcp__claude_ai_Figma__*`. Without it the design-reference rule in
# `skills/jira-ticket` §2 has nothing to open, and design-backed specs fall
# back to whatever the user pastes into the conversation.
#
# Figma's design-to-code skill is the workflow for these tools. It is fetched
# at a pinned commit and hash-checked, not committed: upstream has no licence.
"$(dirname "${BASH_SOURCE[0]}")/../../tools/setup/fetch-figma-skill.sh" || \
  echo "    note: figma-design-to-code skill not installed; rerun tools/setup/fetch-figma-skill.sh"

echo "==> Structurizr MCP server (user scope, all projects)"
# Official hosted instance — DSL validate/parse/inspect plus Mermaid and
# PlantUML export tools. No auth needed for these; server workspace CRUD
# tools require self-hosting instead, not used here.
add_server structurizr --transport http https://mcp.structurizr.com/mcp --scope user

echo "==> Chrome DevTools MCP server (user scope, all projects)"
# Real-browser checks for test-engineer and its figma- copy, the only personas
# whose `tools:` grant mcp__chrome-devtools__* (docs/adr/0070). Executors never get it. Local stdio
# server, no auth. --isolated gives each run a throwaway Chrome profile, so no
# cookies or saved logins reach the agent. Pinned: `@latest` would run whatever
# npm serves that day with full access to the machine (supply-chain.md).
# Needs Node 20+ and a local Chrome. Bump the pin deliberately, here and in
# codex/config.toml together.
add_server chrome-devtools --scope user -- npx -y chrome-devtools-mcp@latest --isolated

echo
echo "Done. Run 'claude mcp list' and confirm each server shows Connected."
echo "A server showing a missing-variable warning needs its token exported in the shell that starts Claude Code."
