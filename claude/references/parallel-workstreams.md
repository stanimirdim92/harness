# Parallel workstreams

`/build` reads this file only when the user asks for parallel workstreams in
the current run; sequential is the default (ADR 0136). Dispatch concurrently,
one executor each, only the workstreams that satisfy ALL of the conditions
below; the rest queue and run sequentially. A condition
that cannot be proved from repository evidence is unmet.

- the user asked for parallel workstreams in this run;
- the plan's Workstreams section fixes the contract between them, and their
  planned files do not overlap;
- the workstreams are genuinely independent (no unfinished dependency between
  them, no shared mutable state);
- each is dependency-ready now (any gating checkpoint has already passed);
- every concurrent writer explicitly requests `isolation: worktree` in the
  dispatch call — never two writing agents against the same checkout;
- **their verification commands do not share mutable runtime state.** A
  worktree isolates git and files; it does not isolate a database, queue,
  cache, search index, or a fixed port. Two suites migrating or truncating one
  database corrupt each other silently — no lock error, just a suite that fails
  for reasons unrelated to its own diff. Dispatch concurrently only when each
  executor has its own instance of every mutable resource its checks touch, or
  when those checks are deferred and run serially at integration. Establish
  which applies from repository evidence, never by assumption;
- the session is not near its rate limit. Concurrent executors share one limit,
  so once throttled, N-wide finishes no faster than a smaller fan-out plus
  queueing, and often slower. When near the limit, reduce the fan-out and queue
  the rest.

"Probably independent" is not established. Each additional executor buys
wall-clock only when unthrottled, truly independent, and runtime-isolated;
otherwise it spends tokens for no speedup, or produces verification results that
cannot be trusted. A condition in doubt is a condition unmet: that workstream
queues. Speed is never bought by skipping or weakening a check.

State the actual dispatch in the completion report: how many ran concurrently,
which workstreams, and how the runtime-isolation condition was satisfied for
each — separate instances, or checks deferred to serial integration. A dispatch
made without establishing that condition is a reportable slip, named as such.

Parallel workstreams still integrate sequentially in dependency order.

Parallelism buys elapsed time, not fewer tokens.
