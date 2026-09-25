# Repository Health Doctor

The Doctor audits repository governance without changing branches, Issues,
labels, rulesets, or repository content. Pull requests run offline fixtures and
local contracts. Live audits run only from the trusted default branch.

## Execution and freshness

Scheduled attempts run at 02:17, 08:17, 14:17, and 20:17 Europe/Berlin. A delayed
attempt still runs: wall-clock lateness is not a reason to discard an otherwise
safe audit. The next scheduled attempt retries an audit deferred by propagation;
manual dispatch is also available. GitHub can delay or drop scheduled events, so
these times are opportunities, not completion guarantees.

Every attempt still checks propagation admission before and after auditing:

- all seven permanent heads and their exact-SHA ancestry;
- same-repository open governed propagation PRs;
- nonterminal parent-qualification runs; and
- a 30-minute grace for unfinished propagation after a recent parent merge.

An active propagation produces `DEFERRED_PROPAGATION`. A propagation PR or
qualification older than two hours fails for inspection instead of deferring
indefinitely. API errors and incomplete activity responses fail closed. A fork
PR cannot suppress the audit. The checked-out trusted event SHA must still be
`main`; a newer `main` produces `DEFERRED_SOURCE_CHANGED`. Moving heads or newly
started propagation invalidate the result as `DEFERRED_REPOSITORY_CHANGED`.
Independent security or contract failures remain failures.

The integrator must avoid starting another propagation during the Doctor.
This admission protocol detects concurrent changes; it is not an atomic lock.

A separate `--freshness` check reads the most recent 100 runs of the registered
Doctor workflow and their JSON artifacts. It accepts only scheduled or manually
dispatched runs from this fork's default branch, with matching workflow path,
repository, source SHA, run ID, and run attempt. It verifies report completeness,
all seven stable heads, and ordered timestamps. A workflow's green conclusion is
never evidence that its audit ran. Failed runs are inspected too: a complete
audit that finds branch drift is fresh evidence of an unhealthy repository.

The reader sorts authenticated run metadata by the latest possible report
completion, including old runs that were rerun recently. Once every remaining
run must be older than the newest verified complete audit, it stops. At most 12
artifact inventories and 12 reports are read per check; an exhausted query
budget reports `UNKNOWN` instead of extending the scan without a bound or
claiming freshness from inconclusive evidence.

The freshness limit is 30 hours. The workflow uploads the audit report first,
then checks freshness even when the audit fails or defers, and uploads the
freshness report. Missing or expired evidence, repeated deferrals, unreadable
artifacts, and malformed reports cannot claim a fresh complete audit. Downloaded
archives are size-limited and read in memory; no member is extracted or executed,
and the GitHub API token is removed before following an artifact redirect.

Freshness reports distinguish:

| Status | Meaning |
| --- | --- |
| `FRESH` | A complete, stable audit finished within 30 hours; consult its separate health result. |
| `STALE` | The latest verified complete audit is older than 30 hours. |
| `MISSING` | No eligible complete report is available in the bounded run history. |
| `UNKNOWN` | Permissions, malformed evidence, or API errors prevent verification. |

Only `FRESH` exits successfully. Its `last_complete_status` may still be `FAIL`.
If GitHub stops scheduling every attempt, no scheduled job can report its own
absence; a later read-only freshness invocation detects the overdue evidence.

## Audit scope and workflow ownership

The seven independently reported areas are branch synchronization and naming,
Issue workflow/WIP and pinned reference #599, governance labels, task-branch
relationships, required workflows, security alerts, and versioned repository
contracts. Configuration is in
[`.github/repository-health.json`](../.github/repository-health.json).
The branch area checks every remote branch name against the shared branch policy,
including branches without a pull request. It accepts permanent branches and
configured scoped, task, reconciliation, promotion and Dependabot names.
An invalid name produces `BRANCH_NAME_INVALID`; an incomplete or malformed
inventory is an operational error, never an empty successful inventory. Existing
invalid branches are reported without an age exemption and are never renamed or
deleted by the Doctor. Local prevention is described in
[the branch-name guard setup](BRANCH_WORKFLOW.md#local-branch-name-guards).

Issue workflow fields are checked only in the current description after the
intake parser verifies any preserved archive and its issue identity. Historical
headings cannot duplicate or supply current next actions, blockers, or unblock
conditions; damaged archives remain audit findings.

Workflow identity uses stable file paths, not display names. Each required
versioned workflow names its owning permanent branch; the Doctor verifies its
active GitHub registration and source file at that branch's exact head. Android
and Apple product-owned workflows are checked on their owning branches, not
incorrectly required in the `main` source tree. Provider-managed Dependabot and
dependency graph workflows use their registered dynamic paths. Retired desktop
topology is not part of the inventory.

The inventory includes the aggregate repository checks, parent qualification,
sync reuse and fallback validation, and dependency-release policy workflows.
An active registration establishes configuration, not successful execution or
freshness. Security workflow summaries therefore show each latest observed
terminal run, explicitly **not necessarily on main**. A failed candidate run
remains visible without making every later repository audit fail. Security
alert counts, workflow availability, complete audit execution, and audit
freshness remain separate evidence; a candidate's conclusion is not silently
promoted to the current default branch's result.

Local contract checks validate only available versioned contracts. All live
areas are `NOT_RUN`, never `PASS`. Local success does not establish the live
repository's state, current security alert counts, or freshness.

## Structured evidence

Audit reports use schema 2 and include `mode`, `status`, `generated_at`,
`audit_executed`, `audit_complete`, `audit_started_at`, `audit_completed_at`,
`source_sha`, `run_id`, `run_attempt`, admission details, and per-area results.
A complete audit requires all areas to run, no unknown permissions or operational
errors, and stable accepted admission. `audit_completed_at` is recorded for a
complete `FAIL` as well as a complete `PASS`. Deferred, local, interrupted, and
operationally incomplete reports cannot refresh this timestamp.

Freshness reports expose `last_complete_at`, `last_complete_status`,
`source_run_id`, `source_sha`, `age_hours` when available, `max_age_hours`, and
`evidence_verification=authenticated_github_artifact`. A saved report remains a
dated snapshot, not a promise that the repository has stayed unchanged.

Acceptance consumers must require a complete live `PASS`, accepted admission,
and their expected source/head set. A recent complete `FAIL`, green deferred
workflow, local contract `PASS`, or merely fresh report cannot satisfy that gate.
The separate branch-sync push observation also uses `PENDING_PROPAGATION` for
normal immediate child lag; its strict scheduled/manual check still detects
unresolved drift.

The Actions summary explains the result. Artifacts are retained for 14 days:
`repository-health-report-<run-id>-<attempt>` and
`repository-health-freshness-<run-id>-<attempt>`. Older schema-1 artifacts do not
establish schema-2 freshness; the first deployed attempt must produce new proof.
This change does not activate any live setting from a local worktree.

## Local checks and authorized live reads

Prepare the Python 3.12 environment with the pinned dependencies in
[`tests/requirements-repository.txt`](../tests/requirements-repository.txt)
using the contributor setup instructions. Both Doctor jobs install that same
dependency list explicitly. After setup, run these without a token or network
access:

```bash
python3 tests/repository-health-test.py
python3 tools/repository-health/check.py --local --report /tmp/repository-health-local.json
```

After the reviewed workflow has been deployed, an authorized live read can use
an appropriately scoped `GITHUB_TOKEN` supplied outside command history:

```bash
python3 tools/repository-health/check.py --report /tmp/repository-health-live.json
python3 tools/repository-health/check.py --freshness --report /tmp/repository-health-freshness.json
```

The workflow uses read permissions, pinned Actions, and checkout without
persisted credentials. Secret-scanning reads require the approved read-only
`REPOSITORY_HEALTH_READ_TOKEN`; falling back to `GITHUB_TOKEN` does not reinterpret
a permission failure as zero alerts. Freshness needs only repository and Actions
reads. Token values are never included in reports.

The Doctor cannot inspect unpushed worktrees, sealed external reports, hardware,
Jenkins state, private dashboard projections, or product behavior without a
corresponding test. Those boundaries are not presented as passing checks.
