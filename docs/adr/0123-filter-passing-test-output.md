# Filter the output of passing test runs

**Context.** The Claude Code cost guide suggests a hook that filters verbose
test output before the agent reads it. A passing suite can print hundreds of
progress lines. The agent needs only the summary. A failing run is different:
the agent needs every failure and stack trace.

**Decision.**
- Add `claude/hooks/filter-test-output.sh` as a PostToolUse hook on Bash.
- Act only when a test runner sits at command position. The rule matches
  `require-isolated-test-runner.sh`.
- Shorten a stream only when it has more than 150 lines. Keep a notice line,
  up to 20 hidden warning lines, and the last 40 lines.
- Replace the output with `updatedToolOutput`. Copy the other fields of the
  Bash result.
- Never shorten a failing run. PostToolUse fires only after success, and the
  hook also skips output that shows a failure marker.
- Leave piped or redirected commands alone. `| cat` is the way to see a full
  passing run.
- Fail open: on any error, the full output stays.
- Claude Code only. Codex has no way to replace a tool's output.

**Rejected — rewrite the command in PreToolUse.** A changed command without a
permission decision can be denied in auto mode, which is this harness's
default mode.

**Rejected — rewrite the command and allow it.** That skips the auto-mode
safety check for every test command.

**Rejected — filter every run.** A failing run needs its full output, and the
summary alone hides which assertion failed.

**Rejected — save the full output to a file.** It writes files the agent did
not ask for, and `| cat` already shows the full output.
