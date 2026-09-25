# Repository maintenance rollout verification

The tooling-first foundation is [PR #937](https://github.com/noah-be/overte/pull/937).
The complete workflow, health, documentation and maintenance implementation is
[PR #938](https://github.com/noah-be/overte/pull/938). Product priorities remain
owned by [the roadmap](../ROADMAP.md).

## Verification sequence

1. Require successful ordinary and governance checks on the implementation PR.
2. In this documentation-only verification PR, introduce one unresolved local
   link and observe both the documentation job and `repository-checks` fail.
   Repair the link before integration and require both checks to pass. The
   project and security jobs must be skipped by the documentation route.
3. Propagate through the six canonical parent-to-child edges with the independent
   `sync-test-reuse` gate. Preserve product-owned sources and test profiles.
4. Export the current live ruleset, add the aggregate requirement without
   removing existing requirements, and read back the saved ruleset.
5. Run the Doctor on the final default-branch commit and verify complete audit
   evidence independently of whether the repository has outstanding findings.

## Evidence boundaries

Fork identity and rejected failure/missing/cancelled results have automated
fixtures in `tests/repository-checks-test.py`, also executed in hosted CI.
A real external-fork PR was not manufactured for this rollout: the authorized
write boundary is `noah-be/overte`. Fixture evidence must not be described as an
observed external-fork event.

A completed Doctor audit may truthfully report preexisting issue-format or
unfinished-branch findings. Preserve those findings and their original work;
completeness and freshness do not mean that the repository has no open work.

Keep final run URLs, exact branch SHAs and the ruleset backup in the rollout
handoff and PR evidence. Do not keep changing shared documentation after every
child merge merely to record synchronization: that would create new drift.

[Repository maintenance guide](../REPOSITORY_MAINTENANCE.md)
