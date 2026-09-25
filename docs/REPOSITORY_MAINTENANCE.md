# Repository maintenance

Use the existing policies, issue intake, repository checks and branch cleanup as
one maintenance loop: inspect, identify the next action, make a focused change,
then verify it. [The roadmap](ROADMAP.md) still owns product priority.

## Local status

From a checkout with local remote-tracking references:

```bash
python3 tools/repository-maintenance/check.py status \
  --report build/maintenance/status.json
```

This command is offline and read-only except for its explicitly requested report.
It does not fetch, read credentials, call GitHub or Jenkins, inspect devices,
merge, prune, delete, or change issues. It shows up to five next actions and keeps
the full detail in JSON. `--max-actions` changes the display limit. `--strict`
returns failure while an actionable or unknown condition remains; a successful
ordinary invocation means that the snapshot was produced, not that GitHub is
healthy. Local remote-tracking refs may be old and are explicitly labelled as
snapshots. The command never silently updates them.

The report covers the six parent-to-child edges, supplied audit/task evidence,
and local worktrees. Locked worktrees, permanent branches, the current checkout,
uncommitted work, detached/unmanaged work and incomplete integration are retained.
Only a clean topic whose complete tip is an ancestor of its owning target can
be listed for integration review. Remote protection, keep requests, unpublished
work elsewhere and recovery requirements are not inferred from local ancestry.
There is deliberately no deletion command or automatic expiry of retention.

## Existing evidence

Provide an already obtained Doctor report without contacting GitHub:

```bash
python3 tools/repository-maintenance/check.py status \
  --health-report build/maintenance/repository-health-report.json \
  --report build/maintenance/status.json
```

Only schema-2 complete live audit or freshness reports can describe a previous
audit. Deferred, local, incomplete, legacy, old and wrong-source evidence remain
distinct. Provided files are not reauthenticated; the report never turns them
into a claim about current remote state. A fresh failed audit remains failed.
The [Doctor](REPOSITORY_HEALTH.md) owns authenticated audit and freshness rules.

An optional `--issues-json` accepts a deliberately supplied snapshot envelope:

```json
{
  "schema": 1,
  "repository": "noah-be/overte",
  "complete": true,
  "generated_at": "2026-09-24T12:00:00Z",
  "issues": [
    {
      "number": 123,
      "state": "open",
      "labels": ["type: task", "workflow: active"],
      "updated_at": "2026-09-24T11:00:00Z"
    }
  ]
}
```

Include every issue needed for the intended working view and explicitly declare
the export complete. Missing or incomplete exports remain unknown. The offline tool reads
workflow names and WIP limits from `.github/issue-policy.json`, counts Now/Next/
Waiting/Inbox and suggests reviewing Active items unchanged for fourteen days.
It never activates, closes or rewrites an issue. Authoritative issue changes
remain with the validated [issue workflow](ISSUE_WORKFLOW.md).

## Keep derived documentation consistent

```bash
python3 tools/repository-policy/check.py
python3 tools/repository-policy/check.py --write
python3 tests/check-documentation.py --all
```

The first command detects policy drift. The second refreshes only explicitly
generated documentation blocks; inspect its diff before committing. It does not
rewrite safety inventories or change branch topology. Documentation checks run
over the current checkout, including incoming links to moved/deleted targets.
They are included in the normal quick test command.

Each fact has a clear owner: branch policy owns hierarchy, issue policy owns work
states, the suite registry owns test entry points, and the roadmap owns product
order. Preserve independent deletion safeguards when checking derived views.

## Required checks

The prepared `Repository checks` workflow starts on every PR without path filters.
Its deployment state is recorded in the dated
[rollout snapshot](maintenance/2026-09-repository-maintenance.md#rollout-snapshot-2026-09-25);
the behavior described here is not evidence of live activation. Its trusted routing
code reads the exact synthetic merge's base and head and never executes candidate
files while deciding which jobs are needed. Markdown-only changes need the full
documentation check. All other ordinary changes need the shared project gate;
workflow and governance changes also need workflow security. Unknown paths take
the full path. The final `repository-checks` job runs even after failures and
rejects missing, cancelled, failed or unexpectedly skipped selected jobs.

Governed same-repository parent/reconciliation shapes delegate project execution
to the independently required `sync-test-reuse` gate. The aggregate still requires
documentation and applicable workflow security. Branch policy and sync-test-reuse
validate direction, exact ancestry, changing refs and candidate-bound tests. Both
the aggregate and the sync gate must remain required in the ruleset. The aggregate
alone is not synchronization evidence. Retargeted PRs rerun both decisions.

The quick suite includes a portable C++ behavior smoke test in addition to syntax,
policy and host contracts. This is not a full application build or device test;
see [test coverage interpretation](../tests/PROJECT_TESTING.md).

## Small recurring maintenance

1. Review the latest complete Doctor result and its independent freshness result.
2. Finish outstanding parent-to-child integrations through the normal reviewed
   [branch workflow](BRANCH_WORKFLOW.md); no child-to-parent shortcuts.
3. Review Active/Ready issue state through the existing intake tool. Treat old
   handoffs as review requests, not instructions to restart work automatically.
4. Let [branch cleanup](AUTOMATIC_BRANCH_CLEANUP.md) retire only fully integrated
   remote topics under its existing protections and backup protocol.
5. Inspect local worktrees separately. Preserve unfinished experiments and avoid
   archive tags when the integrated history already remains reachable.

After PHONE-P1, use measured synchronization cost to evaluate intermediate branch
responsibilities. An optional `--effort-log` reads an envelope with `schema: 1`,
`repository: "noah-be/overte"`, and `changes`. Each change has a unique full
`commit`, positive `maintenance_minutes`, `propagation_minutes` between zero and
that total, and boolean `manual_reconciliation`. Over the last ten observations,
more than 20% propagation effort or at least three reconciliations suggests a
topology review. This is advisory; it never authorizes branch retirement.

## Deployment

Local implementation and tests do not activate workflows or live rulesets.
The trusted router and verifier intentionally do not fall back to unreviewed PR
code. Consequently the initial rollout must stage the trusted helper/configuration
on `main` before relying on the aggregate workflow. Prepare a tooling-first change
with its offline tests, followed by orchestration and the complete desired
ruleset. Keep existing checks active throughout.

The September 2026 rollout is authorized and underway. Its
[dated record](maintenance/2026-09-repository-maintenance.md) distinguishes local
preparation, an open foundation PR, and the remaining deployment steps. Follow
this sequence without treating a prepared manifest as an applied setting:

1. **M1 — Establish the baseline.** Inspect current fork `main`, preserve the
   current product roadmap, and reconcile local implementation with that source.
2. **M2 — Stage trusted routing.** Integrate the helper/configuration and their
   tests on `main` before adding the aggregate workflow. Keep existing workflows
   and required contexts active. Qualification inputs must name only files that
   exist in this foundation; add the remaining inputs with the full integration.
3. **M3 — Integrate and propagate.** Integrate the complete workflow wiring and
   tools, then propagate through all six edges, preserving product-owned suites,
   sources and manual workflows. Existing rulesets use strict required checks.
   Prefer the [attested reconciliation path](BRANCH_WORKFLOW.md#reconciliation-merges)
   when a direct parent PR cannot satisfy the target's up-to-date requirement.
   Keep strict protection and all existing checks; never reverse-merge a
   permanent child into its parent to make a parent PR current.
4. **M4 — Verify workflow behavior.** Seed `repository-checks` and verify ordinary,
   documentation, governance and governed-sync paths on Actions. Confirm failed,
   missing and invalidly skipped selected checks cannot pass aggregation. Use
   fork-identity fixtures on Actions without writing to an external fork.
5. **M5 — Activate and audit.** Resolve actual fork ownership and the live ruleset
   ID, export a rollback copy, and add `repository-checks` alongside every existing
   required context without relaxing strictness or other rules. Read back the
   complete saved settings. Obtain a complete schema-2 Doctor report and verify
   its freshness against current source and workflow identities; old schema-1
   green runs do not establish freshness.

Keep subsequent rollout results in PR and workflow evidence with exact revisions
and read-back results. Rewriting shared status documentation after every child
merge would introduce another synchronization cycle. The
[implementation and rollout record](maintenance/2026-09-repository-maintenance.md)
preserves the original local evidence and the dated starting snapshot.
