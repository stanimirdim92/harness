# Subagent model pins enforced, frontmatter fields checked, executor cache 1h

**Context.** The subagents doc (https://code.claude.com/docs/en/sub-agents,
read 2026-11-10) states three facts that affect this harness:
- Since v2.1.251, a per-call Agent `model` beats the frontmatter `model` pin.
- Claude Code silently ignores an unknown frontmatter field.
- `experimental.cacheTtl` (`5m` or `1h`) sets a subagent's prompt-cache TTL.

**Decision — enforce pins with a hook.** `claude/hooks/require-pinned-model.sh`
runs as a PreToolUse hook on `Agent|Task`. A per-call `model` must be a
strictly higher tier than the persona's pin. The tier order is haiku, sonnet,
opus, fable. A same-tier alias is denied: `sonnet` floats past the
`claude-sonnet-5-5` pin, and `opus` drops `[1m]`. This turns the CLAUDE.md
rule "override upward only" into a check. Calls without `model` and agents
without a file in `claude/agents/` pass. The hook fails closed without jq
([0087](0087-guards-fail-closed-without-jq.md)).

**Decision — reject unknown frontmatter fields.**
`tools/checks/validate-frontmatter.py` fails on any top-level key outside the
documented set. A typo such as `maxturns` would otherwise drop a gate with no
error.

**Decision — 1h cache for executors only.** `executor` and `figma-executor`
set `experimental: { cacheTtl: 1h }`. `/build` resumes them between tasks. We
assume these gaps often exceed five minutes; no run metric measures them yet.
Reviewers, recon and test-engineer run once, so a longer TTL only raises their
cache-write cost.

**Rejected — *`CLAUDE_CODE_SUBAGENT_MODEL_FORCE`.*** It forces one model on
every subagent. The harness tiers models by role
([0056](0056-role-tiered-models-blind-review-recon-width-writer-isolation.md)).

**Rejected — *deny every per-call model.*** CLAUDE.md allows an upward
override for high-risk work.

**Rejected — *1h cache on every persona.*** One-shot agents never reuse the
cache after five minutes.

**Revisit if.** Run metrics in `docs/observation-log.md` show executor resumes
mostly within five minutes. Then the 1h TTL only adds write cost.
