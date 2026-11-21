# Reviewer trigger matrix

Single source of truth for `/review` specialist dispatch.

- **`code-reviewer`** — always.
- **`blind-reviewer`** — always. The same diff read with no intent at all; see
  the packet rule below, which is what makes it a second opinion rather than a
  second copy.
- **`security-auditor`** — always, on every review round (ADR 0102). It
  goes deepest where the diff changes a security boundary:
  authentication/authorization, permissions, tenant isolation,
  secrets/credentials, cryptography, untrusted-input handling, sensitive data
  exposure, dependency/supply-chain trust, or security-sensitive infrastructure
  / third-party integration behavior. On a diff that touches none of these, it
  says so in one line and stops.
- **`distributed-systems-reviewer`** — only when the diff materially changes
  distributed failure semantics. These are retries, idempotency, ordering,
  delivery guarantees, concurrency, timeout/failover behavior, queue
  processing, multi-step/background-job recovery, or state coordination across
  a process/network boundary.

A change that touches a path in the project's "Always a person" list
(`always-person.py`, ADR 0096) runs `distributed-systems-reviewer` too,
whatever the diff's content.

A generic config edit, ordinary HTTP call, existing worker touch, or third-party
integration does **not** trigger a specialist merely because that category is
present. The change must alter a failure/trust boundary the specialist owns.

What each reviewer receives is defined once, in `/review` §3.
