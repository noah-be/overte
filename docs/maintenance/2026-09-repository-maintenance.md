# Repository maintenance implementation and rollout record

This records the September 2026 repository audit's local implementation and
subsequent rollout. It does not change product priority in
[the roadmap](../ROADMAP.md). Implementation is AI-assisted. Local test results
and verified remote integration are recorded separately.

## Rollout snapshot: 2026-09-25

The rollout was authorized after the original local implementation. Its M1–M5
steps below are deployment steps, distinct from the five implementation
deliverables recorded later in this document.

| Rollout step | Outcome | State at this snapshot |
| --- | --- | --- |
| M1: Establish the current baseline | Reconcile the implementation with the current fork `main` | Baseline verified at [`d9ab1c1c64`](https://github.com/noah-be/overte/commit/d9ab1c1c641cf6fe749b5ec9aac0acf2e85f6e73); current product roadmap retained |
| M2: Stage trusted routing | Put the router, configuration, focused tests and qualification inputs on `main` before workflow activation | [PR #937](https://github.com/noah-be/overte/pull/937) opened from `c6c6aa3d90963d5b6d11371589fcdfcf1c18bd45`; local validation passed, remote checks and merge pending |
| M3: Integrate and propagate | Integrate the complete system, then propagate through all six parent-to-child edges | Pending; preserve product-owned sources and tests, prefer attested reconciliation under existing strict rules |
| M4: Verify workflow behavior | Verify ordinary, documentation, governance and synchronization paths, including failed aggregation and fork-identity fixtures on Actions | Pending; fork-identity fixtures require no writes to an external fork |
| M5: Activate and audit | Back up the live ruleset, add the required aggregate context, read back settings, and obtain complete schema-2 Doctor and freshness evidence | Pending; preserve every existing required context and strict setting |

M2's foundation passed these local commands before PR submission:

- `python3 tests/run-project-tests.py --profile quick --timeout 240`: 17 groups,
  zero failures.
- `python3 tests/repository-checks-test.py`: 11 focused tests passed.
- `python3 tools/sync-test-reuse/test.py`: 24 tests passed.

The foundation intentionally retains the existing workflows and live-check
requirements. Its tests cover the staged state; the full integration restores
the final workflow, ruleset and qualification assertions. Local success does
not establish that PR #937 has passed its remote checks or merged.

The rollout inspection confirmed strict required checks in the existing live
permanent, Android and Apple rulesets. Earlier branch-governance prose claiming
that parent synchronization did not need an up-to-date head was inconsistent
with those settings and the versioned manifests. M3 uses child-based, attested
reconciliation when direct parent PRs cannot satisfy strict checks; it does not
relax protection or merge a permanent child into its parent.

This is a dated snapshot, not a live dashboard. Record subsequent completion in
the rollout's PR and workflow evidence, including exact source revisions and
read-back results. Do not repeatedly change shared documentation merely to
record each propagation step and thereby create another propagation cycle.

## Historical local scope and boundaries

The following scope governed the original local-only implementation. The later
rollout authorization superseded its prohibition on remote work; the recorded
local results remain historical evidence.

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

## Historical local implementation milestones

| Milestone | Deliverable | Acceptance | State |
| --- | --- | --- | --- |
| M1: Trustworthy merge checks | Correct failure propagation, complete PR routing, required aggregate gate and ruleset manifest | Relevant failed, missing, cancelled or invalidly skipped checks cannot satisfy the gate; governed synchronization remains supported | Complete locally; tests passed |
| M2: Reliable repository health | Executed/deferred/unknown/stale states, durable full-audit freshness, current workflow inventory | Fixtures exercise delays, propagation, failures and stale evidence; local-only areas are never presented as live passes | Complete locally; tests passed |
| M3: Developer entry | Correct build/test guidance, branch-aware entry links and task-oriented documentation index | A contributor can find the owning branch, prerequisites, first check and code entry point | Complete locally; links and source references checked |
| M4: Maintainable structure | Component map, consistent policy views and robust documentation validation | Policy changes expose stale derived views; links/anchors and removed targets are checked without interpreting code as prose | Complete locally; tests passed |
| M5: Routine maintenance | Concise offline repository/worktree status, safe actionable plans and maintenance guide | Drift, stale/unknown evidence and retained unintegrated work remain visible; no automatic deletion or external writes | Complete locally; tests passed |

## Historical local verification plan

1. Run focused tests for each changed subsystem, including deliberately invalid
   inputs and subprocess exit-status checks.
2. Run full offline documentation and policy consistency checks.
3. Run `python3 tests/run-project-tests.py --profile quick --timeout 240` and
   relevant hardware-independent device contracts.
4. Validate workflow YAML/action pins and required-gate/ruleset contracts.
5. Exercise the maintenance CLI in this worktree and temporary repositories.
6. Run `git diff --check`, review the complete diff, and record exact results.

## Historical local decisions and discoveries

- During the local-only stage, the audit's live ruleset activation and two
  outstanding remote synchronization edges could not be changed. That stage
  supplied tested manifests, local drift inspection and a deployment checklist;
  it did not establish synchronized remote state.
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

## Historical local completion evidence

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
These local results establish neither a complete application build nor
physical-device acceptance or live GitHub activation.
