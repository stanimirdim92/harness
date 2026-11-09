# Worktrees

The full worktree rules. `AGENTS.md` §Worktrees keeps only the defaults every
session needs and points here.

Ticket-scoped work defaults to one isolated worktree per ticket.

- Start it with `claude --worktree <ticket>` or, in the Codex CLI,
  `codex-worktree <ticket>` from the project. The Codex launcher uses
  `.codex/worktrees/<ticket>` in the main checkout and a `codex/<ticket>` branch;
  different tickets run as independent sessions in separate terminals. In the
  desktop app, choose Worktree in a new chat and attach a branch before writers.
  Claude's `worktree.baseRef` is `head` here, so the worktree branches from the
  local `HEAD` you start from. **Pull first:** starting from a stale `main`
  gives a ticket branch stale by the same amount, and the worktree is created
  successfully either way.
- Sequential executors inherit the ticket checkout. Explicitly request
  `isolation: worktree` for each concurrent writer; preserve independent
  reviewer contexts and the test-engineer's isolated checkout. `head` makes
  those child worktrees inherit the session's ticket commits (docs/adr/0058).
- Two hooks protect the session boundary (docs/adr/0057, 0058). Session start
  warns about a stale default branch or a fresh ticket without its own commits.
  Separately, an optional project `bin/worktree-doctor.sh --infrastructure`
  reports outdated runner infrastructure even mid-ticket. Writing dispatch is
  denied on the main checkout's default branch, detached HEAD, unverifiable
  input/Git state, or failed infrastructure readiness. Valid read-only personas
  remain unrestricted. Reconcile the reported infrastructure changes without
  merging unrelated ticket work.
- Claude Code places managed worktrees in `.claude/worktrees/`, which belongs in
  the project's `.gitignore`. Prefer that location: `.worktreeinclude`,
  subagent `isolation: worktree`, and the cleanup sweep only apply there.
  The Codex CLI launcher separately manages `.codex/worktrees/`, excludes it
  locally, copies `.worktreeinclude` files, and retains checkouts after exit.
- Gitignored files a worktree needs — `.env`, local config, credentials
  templates — go in a project-root `.worktreeinclude` using gitignore syntax.
  Claude Code and Codex both copy matching **ignored** files into every managed
  worktree; tracked files are never duplicated. A `WorktreeCreate` hook replaces
  this, so copy inside the hook script instead. Copies are a cache, not proof
  of readiness. Dependency directories must belong to the checkout, never
  shared symlinks.
- A worktree is a fresh checkout: dependencies are not installed and no build
  or test command works until they are. Specification and planning work needs
  none of them; anything that builds, tests, or lints does.
- Use `git worktree add` directly only to check out an existing branch or to
  place a worktree outside the repository; the Codex launcher owns creation
  inside its dedicated directory. Remove with `git worktree remove`,
  never `rm -rf` — that strands metadata, recoverable with `git worktree prune`.
- A branch lives in exactly one worktree. Free it with `git worktree remove`
  before checking it out elsewhere.
- In a worktree session, Claude Code refuses commands it cannot prove stay
  inside the worktree. Each refusal costs a retry. Avoid the refused forms:
  - Resolve `$HOME` once (`echo $HOME`). Then write literal absolute paths,
    such as `python3 /home/<user>/.claude/skills/...`. Never pass `"$HOME/..."`
    as an argument. Harness examples write `~/.claude/...`; replace `~` too.
  - Write and change files with Write or Edit, not a heredoc or a script.
  - Run each git command on its own, not inside `;`, `&&` or a heredoc.
    Write a long commit message to a file with Write, then run
    `git commit -F <file>`.
- Concurrency is bounded by the conditions in `../commands/build.md`, not by a
  fixed count. Worktrees isolate git and files only; a database, queue, cache,
  or fixed port is still shared, and concurrent writers need their own instance
  of every mutable resource their checks touch.
