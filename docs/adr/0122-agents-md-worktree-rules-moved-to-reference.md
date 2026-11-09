# Worktree rules moved from AGENTS.md to a reference

**Context.** Every Claude and Codex session loads `claude/AGENTS.md`. The
Claude Code cost guide advises a CLAUDE.md under 200 lines. The file had 265
lines. Its §Worktrees section had 60 lines, and most of them apply only when a
session sets up or runs in a worktree. §Agent orchestration repeated the
executor reuse rule from `commands/build.md` §2.

**Decision.**
- Move the full §Worktrees text, unchanged, to `claude/references/worktrees.md`.
- Keep a short §Worktrees stub in `AGENTS.md`: one worktree per ticket, pull
  first, and read the reference before git or shell work in a worktree session.
- Cut §Agent orchestration to the general rules. Point to `commands/build.md`
  §2 for executor reuse.
- Keep the section headings, because commands and skills cite
  `AGENTS.md` §Worktrees and §Agent orchestration.
- Write harness pointers in `AGENTS.md` as `~/.claude/...` paths. Codex loads
  the same file as `~/.codex/AGENTS.md`, where `references/...` points into
  `~/.codex/references`. The Codex agent files already use `~/.claude/...`.
- Rephrase §Writing for humans in fewer lines. The rules and limits stay.

The file now has 209 lines.

**Rejected — move §Writing for humans to a reference.** It would bring the
file under 200 lines. Its rules apply to every report and update, so a session
must see them without a lookup.

**Rejected — shorten rules 1 to 8.** `harness-map.py` parses their headings,
leads and *Catches* lines, and they are the core rules.
