# Remove the /explain command

**Decision.** `/explain` is removed: `claude/commands/explain.md`, its Codex
adapter `codex/skills/explain/`, and its mentions in the README, the
contracts doc, the `spec-driven-development` pipeline diagram, the harness
map and two checks. It added an offline HTML review page outside the gates
([0069](0069-plain-writing-explain-page-and-generated-map.md)). The rest of
0069 stands.

The reason is use. A scan of 186 leadbuster sessions on 2026-11-21 found one
`/explain` run since it was added on 2026-10-03 (LD-365, 2026-11-13), against
55 `/review` and 29 `/ship` runs. Its 729 words still had to be kept true to
every change in the gate artifacts it read. The owner decided to remove it
during the command pruning audit.

**Rejected — *keep it unused.*** Every gate change must still keep the page
correct, and the harness is trying to shrink its command text.

**Revisit if** the owner reviews candidates outside the terminal often enough
to want one page per candidate again; recover the file from git history.
