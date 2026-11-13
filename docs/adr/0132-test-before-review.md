# `/test` runs after every `/build`, before `/review`

**Decision.** The pipeline order is `/build` → `/test` → `/review` → `/ship`
(owner's call, 2026-11-13).

- `/test` runs after every `/build`. It checks the candidate against
  `verification-triggers.md` and decides whether it is exempt. An exempt
  candidate gets **VERIFY NOT REQUIRED** with the exemption named, and no
  verifier is dispatched.
- `/review` requires `/test`'s result for the exact candidate. It checks an
  exemption again and blocks when the exemption does not hold.
- A review fix goes back through `/build`, `/test` and `/review`.
- Every command waits for every agent it dispatched before it ends its turn
  (`AGENTS.md` §Agent orchestration). This covers `/build`'s executors and
  the recon agents of `/spec` and `/plan` too.

This moves the decision point of [0104](0104-test-runs-every-production-change.md)
and [0035](0035-independent-verify-made-risk-triggered.md) from `/review` to
`/test`. The exemption list does not change.

The runners and `docs/agents.md` already used this order. The commands said
`/review` decided, so a manual run went `/build` → `/review` → blocked →
`/test` → `/review`.

In the LD-536 experiment (2026-11-13), a headless `/test` ended its turn while
its verifier ran in the background. The session exit killed the verifier,
and the next `/review` blocked. The foreground rule prevents that.

**Rejected — *`/build` names the next stage.*** It splits the exemption
decision away from the gate that verifies.

**Rejected — *no exemptions.*** A docs-only change would pay for a verifier
run.
