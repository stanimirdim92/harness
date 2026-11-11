# repo-recon writes its report to a file

**Decision.** `repo-recon` gets the Write tool. The hook
`claude/hooks/limit-recon-write.sh` limits Write to one path:
`docs/specs/[TICKET]-recon-[area].md`. Recon writes its full report there.
Its reply holds only the path, the hit count per section and the key
Unknowns. The caller reads only the report sections it needs. Owner's call,
2026-11-11.

The reason is tokens. In the LD-520 `/spec` run, the recon reply was 35.7k
chars, about 10k tokens. Every later main-session turn then read those tokens
from cache again. The report must list every hit, so a shorter report is not
an option.

`tools/checks/validate-frontmatter.py` allows Write for recon only when the
hook is in its frontmatter. Codex runs the same persona in a read-only
sandbox. There, recon returns the full report as its reply.

This narrows [0041](0041-recon-delegated-to-repo-recon-subagent.md) and
[0055](0055-multi-agent-enforcement-and-parallel-when-safe.md): recon is no
longer read-only by tool grant. It still cannot run commands or edit source.

**Rejected — *Option B: a capped, short report with no Write.*** The owner
requires every hit in the report. A cap drops hits that `/plan` needs.

**Rejected — *the caller saves the reply to a file.*** That saves nothing. The
reply is already in the main context when the caller saves it.

**Rejected — *run Explore first, then recon.*** Explore can miss a hit, and
recon may then not look for it. Personas also cannot dispatch personas
(0055).

**Revisit if.** Recon cannot write in practice (a permission prompt or a
denied path), or the caller reads the whole file on most runs.
