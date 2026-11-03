# Figma tools only in figma- copies of executor and test-engineer

**Context.** A subagent has no tool search, so every MCP tool its `tools:`
grants loads in full on every call. The Figma server has about 40 tools.
Loaded in this session, their definitions took 39,126 cache-write tokens,
so about 37k per subagent call. Executor first calls grew from about 35k to
about 70k after Figma was added (2026-10-03, c353ab7). On LD-521 the first
call was about 81k for an executor and 87k for a verifier, against about 23k
for a reviewer. Of 78 executor and verifier runs, 4 called a Figma tool, all
on UI tickets (LD-507, LD-503). On LD-521, a backend ticket, executors and
verifiers made about 618 calls, so Figma cost about 20M of 113M Sonnet tokens.

**Decision.**
- `executor` and `test-engineer` grant no Figma tools.
- `figma-executor` and `figma-test-engineer` are copies with `mcp__figma__*`
  added. `/build` dispatches `figma-executor` when the task's spec or packet
  links a Figma design. `/test` dispatches `figma-test-engineer` when an
  in-scope claim is "matches the Figma design". All other dispatches use the
  base persona.
- `validate-frontmatter.py` keeps each copy equal to its base: the same body
  and the same frontmatter except name, description and the Figma tools. A base
  persona that grants Figma tools fails. The worktree and handoff guards list
  both copies, and their tests prove a copy is guarded.
- Codex is unchanged. Its roles gate Figma through `codex/hooks/policy.py`,
  not through Claude's `tools:` line.

**Rejected.**
- Keep Figma on both personas: about 37k tokens on every call of the 95% of
  runs that never use it.
- The main session fetches Figma context into files before dispatch: the
  design-to-code and verification workflows query nodes while they work, and
  the main session would have to guess which nodes the agent needs.
- One body shared by include: Claude Code agent files have no include, so
  the parity check replaces it.

**Cost.** Two persona files that must change together; the validator fails
when they do not. Every guard that names a writer persona must name the
copies too. Measure the result with `run-metrics.sh` PER AGENT: the first
context of a base executor should fall by about 37k.
