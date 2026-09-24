# Repository maintenance implementation plan

This is the local implementation and verification record for the September 2026
repository audit. It does not change the product priority in [the roadmap](../ROADMAP.md).
Implementation is AI-assisted and is reviewed and tested locally.

## Scope and boundaries

- Work on `refactor/main/repository-self-maintenance`, based on
  `616acca5cf5390f41babd9b55bba221900c81f35`, in a separate worktree.
- Implement all five audit roadmap improvements as one reviewable local result.
- Do not push, change GitHub settings or issues, dispatch workflows, operate
  Jenkins/devices, delete branches/worktrees, or integrate permanent branches.
- Prepare and test versioned rulesets and workflows; their later deployment is
  distinct from local implementation and must not be claimed as completed here.
- Preserve the seven-branch source boundary and existing conservative cleanup.
- Use fixture-driven negative tests for governance and safe temporary Git
  repositories for local maintenance tests.

## Milestones

| Milestone | Deliverable | Acceptance | State |
| --- | --- | --- | --- |
| M1: Trustworthy merge checks | Correct failure propagation, complete PR routing, required aggregate gate and ruleset manifest | Relevant failed, missing, cancelled or invalidly skipped checks cannot satisfy the gate; governed synchronization remains supported | Complete locally; tests passed |
| M2: Reliable repository health | Executed/deferred/unknown/stale states, durable full-audit freshness, current workflow inventory | Fixtures exercise delays, propagation, failures and stale evidence; local-only areas are never presented as live passes | Complete locally; tests passed |
| M3: Developer entry | Correct build/test guidance, branch-aware entry links and task-oriented documentation index | A contributor can find the owning branch, prerequisites, first check and code entry point | Complete locally; links and source references checked |
| M4: Maintainable structure | Component map, consistent policy views and robust documentation validation | Policy changes expose stale derived views; links/anchors and removed targets are checked without interpreting code as prose | Complete locally; tests passed |
| M5: Routine maintenance | Concise offline repository/worktree status, safe actionable plans and maintenance guide | Drift, stale/unknown evidence and retained unintegrated work remain visible; no automatic deletion or external writes | Complete locally; tests passed |

## Verification plan

1. Run focused tests for each changed subsystem, including deliberately invalid
   inputs and subprocess exit-status checks.
2. Run full offline documentation and policy consistency checks.
3. Run `python3 tests/run-project-tests.py --profile quick --timeout 240` and
   relevant hardware-independent device contracts.
4. Validate workflow YAML/action pins and required-gate/ruleset contracts.
5. Exercise the maintenance CLI in this worktree and temporary repositories.
6. Run `git diff --check`, review the complete diff, and record exact results.

## Decisions and discoveries

- The audit's live ruleset activation and two outstanding remote synchronization
  edges cannot be changed under the local-only instruction. This implementation
  supplies tested manifests, local drift inspection and a deployment checklist;
  it does not manufacture synchronized remote state.
- Existing issue intake and branch cleanup already perform deterministic repair
  and conservative retention. Extend their visibility rather than introduce a
  second issue writer or a less conservative deletion mechanism.
- The shared suite table excludes branch-owned product entries so forward merges
  do not require rewriting shared documentation on each product branch. Product
  entries remain available with `--platform-only --list`.
- The aggregate uses one trusted routing decision and reusable workflows with
  distinct concurrency groups. Documentation-only routing also checks Git file
  modes; executable Markdown, symlinks and gitlinks take the full route.
- New governance tools and configuration are included in parent-qualification
  inputs, so synchronization cannot reuse evidence that omitted their changes.
- The Doctor's YAML dependency is now an explicit pinned Python prerequisite
  across shared CI, parent qualification, sync fallback and Doctor jobs.
- Reviews found and fixed Markdown reference/indentation/anchor edge cases,
  duplicate policy inputs, symlink destinations, report overwrite hazards, dirty
  submodules, nullable snapshots and non-finite numeric observations.

## Completion evidence

The complete quick suite passed: **24 groups, zero failures** (99.68 seconds).
It includes full workspace documentation, generated policy consistency, a
portable production C++ smoke test and the following focused checks:

- `python3 tests/repository-checks-test.py`: 13 tests passed after final routing
  hardening (exact merge identity, bad/missing/cancelled results, concurrency,
  executable Markdown and qualification inputs).
- `python3 tests/repository-health-test.py`: 59 tests passed.
- `python3 tests/documentation-test.py`: 24 tests passed.
- `python3 tests/repository-policy-test.py`: 12 tests passed.
- `python3 tests/repository-maintenance-test.py`: 16 tests passed, including
  temporary Git worktrees, holds, dirty submodules, missing paths and overwrite
  rejection.
- `python3 tools/sync-test-reuse/test.py`: 24 tests passed after extending the
  qualification inputs.
- `python3 tests/check-documentation.py --all`: 182 workspace Markdown files
  passed; remote URLs were not fetched.
- `python3 tools/repository-policy/check.py` and
  `python3 tools/workflow-security/check-action-pins.py`: passed.
- Actionlint 1.7.12, offline Zizmor 1.30.0 and redacted Gitleaks 8.30.1 passed.
  Binaries were obtained from existing local archives after verification against
  the workflow's recorded SHA-256 values; no download or system install occurred.
- `python3 tools/repository-maintenance/check.py status --report build/maintenance/status.json`:
  produced a read-only local snapshot and correctly showed two delayed edges,
  unknown live evidence, and retained worktrees.
- `git diff --check`: passed.

Independent read-only inspection of local remote-reference documentation found
no target/anchor findings across Android Phone (257 documents), Pico (252) and
iOS (234). It used `git ls-tree`, `git show`, and the new parser without fetching
or checking out those branches. Shared generated JSDoc links were validated by
the workspace checker. This does not replace tests of later merged candidates.

The full hardware-independent control-plane suite also passed: **22 groups,
zero failures, zero skips** (368.35 seconds), including host C++/Qt contracts,
Python fixtures and QML contracts. Results are stored locally in
`build/test-results/maintenance-project-tests.xml` and
`build/test-results/maintenance-device-full.xml`.
No complete application build, physical-device acceptance or live GitHub
activation is claimed by this maintenance change.
