# Review findings

The single definition of a review finding's disposition and of the review
SARIF. Reviewers, `/review` and `/ship` read this file. It is short on purpose:
read it whole. The other output contracts are catalogued in
`component-response-contracts.md`, which maintainers read and no stage loads.

## Dispositions

| Disposition | Means | `/ship` resolves it by | SARIF level |
|---|---|---|---|
| BLOCKER | Incorrect behavior, data loss, a security exposure, or a broken contract | a fix; a suspected (low-confidence) one also by recorded refuting evidence | `error` |
| REQUIRED | A defect to fix before merge: an unhandled path, a missing test, a weak contract | a fix, refuting evidence, accepted risk, or a deferral with a reason | `warning` |
| ADVISORY | An optional improvement | nothing; it never blocks | `note` |

`blind-reviewer` also returns intent-dependent findings with no disposition
yet; `/review` gives each one a disposition or closes it. This table is the
only definition: personas, `/review` and `/ship` point here.

**Failure scenario.** Every BLOCKER and REQUIRED finding names one: the
input, state or timing, and the wrong result it produces. A claim with no
nameable failure scenario is ADVISORY at most, or goes under Not verified. The
independent check in `/review` tests this scenario.

**Pre-existing.** A finding is marked `pre-existing` when the defect already
exists at the candidate base and the change neither introduces it nor makes it
reachable or worse. It keeps its disposition, so its seriousness stays visible.
It does not block `/ship`; `/ship` records it as a follow-up. A change that
adds a caller of the old defect, copies it, or depends on it makes it new, and
then it is not pre-existing (ADR 0090).

## Review SARIF

`/review` also writes its findings as SARIF 2.1.0 (OASIS), in one file per
ticket: `docs/reviews/<TICKET>.sarif` (ADR 0145). Each round appends one run
per reviewer; the disposition decides `level` (§Dispositions). Every run
carries `round`, `approach`, `reviewedCommit` and `closing` in its
`properties`. A round counts toward the round-4 stop when it is not a closing
round and belongs to the current approach, the highest one in the file. The
stats scripts count the non-closing rounds of every approach. Read and write
the file with `review-sarif.py`; never load it whole. `latest --all --open`
lists the open findings of every round:

```json
{
  "version": "2.1.0",
  "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
  "runs": [{
    "tool": {"driver": {"name": "code-reviewer"}},
    "automationDetails": {"id": "review/LD-1/a1r1/code-reviewer"},
    "properties": {"round": 1, "approach": 1, "reviewedCommit": "abc1234", "closing": false},
    "results": [{
      "ruleId": "CODE-1",
      "level": "error",
      "message": {"text": "problem + recommended fix"},
      "locations": [{"physicalLocation": {
        "artifactLocation": {"uri": "app/Services/Feed.php"},
        "region": {"startLine": 42}}}],
      "baselineState": "new",
      "properties": {"disposition": "BLOCKER", "confidence": "high",
                     "requirement": "REQ-003", "resolution": "open",
                     "verification": "CONFIRMED", "class": "missing-tenant-scope"}
    }]
  }]
}
```

`baselineState` is `unchanged` for a pre-existing finding and `new` otherwise.
`verification` is the BLOCKER check's verdict (CONFIRMED, REFUTED or UNSURE);
other findings omit it.
`resolution` is `open`, `fixed`, `refuted` (the claim is false), `answered`
(the approved spec answers it, or it restates the owner's request; never a
BLOCKER), `accepted`, `deferred`, `follow-up` or `declined`. `/review` sets
`answered`; `/ship` sets the rest. `review-noise.py` counts `answered` as
neither a finding fixed nor noise.
`aliases` lists the other ids of a duplicate group (`["BLIND-7"]`). Each id
stays its own result.
`class` is a short kebab-case name for the kind of defect, the same name for
the same kind on every ticket. Reuse a name from `review-noise.py --classes`
when one fits; coin a new one only when none does (ADR 0105).
`uri` is relative to the repository root. A finding without a line keeps the
`artifactLocation` and drops `region`; one without a file drops `locations`.
`properties` keeps what SARIF has no field for, so nothing in the markdown
report is lost.
