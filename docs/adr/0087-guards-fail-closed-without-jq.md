# Command guards fail closed without jq

**Context.** The five PreToolUse command guards read their input with `jq`.
When `jq` was missing, each hook crashed with exit code 127. Claude Code
blocks a tool call only on exit code 2 or a deny decision, so the crash
allowed the command. A test showed `rm -rf /` passing
`block-destructive-bash.sh` this way. Git for Windows ships no `jq`, so a
native Windows install hit this on every command. A Linux or macOS machine
without `jq` hit it too.

**Decision.**
- `block-destructive-bash.sh`, `warn-force-push.sh`, `block-agent-push.sh`,
  `require-commit-trailers.sh` and `require-isolated-test-runner.sh` check for
  `jq` before they read input. Without it, each prints a fixed deny decision
  that needs no `jq` and names the fix.
- This follows `require-worktree-for-writers.sh`, which already denied when
  it had no JSON parser (ADR 0058).
- `test-hooks.sh` runs every guard with `jq` off the PATH and expects deny.

**Rejected.**
- Exit code 2 with a message on stderr. It also blocks, but the guards
  already answer with JSON decisions. One response shape is easier to test.
- Failing closed in `require-handoff-report.sh`. It checks the shape of a
  report, not the safety of a command. Its design allows on any read failure
  so that a broken hook cannot stop a build. Without `jq` it cannot read its
  own block counter, so a block could repeat without limit.
- Failing closed in `warn-stale-base.sh`. It only warns at session start.

**Cost.**
- A machine without `jq` cannot run any shell command until `jq` is
  installed. The deny reason says so.
- `warn-force-push.sh` now denies where it would have asked.

**Amendment (2026-11-13).** Every `PreToolUse` guard also sets
`onFailure: "block"`, in `claude/settings.json` and in the agent
frontmatter. The runtime then blocks the action when a guard cannot start,
crashes, times out or prints invalid JSON. The `jq` check above covers only
one of those failures. A guard that works is unaffected: it still exits 0
with its JSON decision. The setting has no effect on `SubagentStop`, so
`require-handoff-report.sh` keeps its fail-open design. Source: the Claude
Code hooks and security docs; checked in the installed 2.1.323 binary.
