# Repository Health Doctor

The Repository Health Doctor is a fail-closed, read-only audit of repository
governance. It is scheduled at02:17 Europe/Berlin and can be dispatched manually. Pull requests run
only local fixture and contract tests; live GitHub queries run only after the
workflow checks out the trusted default branch.

The audit checks these independently reported areas:

- all eight parent-to-child edges in the permanent branch hierarchy from
  [the branch policy](../.github/branch-policy.json);
- the GitHub Issue task SSOT, workflow-label rules, Ready and Active WIP limits,
  blocked-task details, and pinned reference Issue #599;
- the exact names, colors, and descriptions of the six governance labels;
- `task/<scope>/<issue>-<slug>` branches, their Issues, duplicates, orphaned
  branches, and open pull-request association;
- the presence and active state of required workflows;
- open CodeQL, Dependabot, and secret-scanning alerts, grouped where applicable,
  plus the latest terminal state of central security workflows;
- versioned branch, ruleset, workflow, action-pin, permission, and secret-safety
  contracts.

Configuration and expected label values live in
[`.github/repository-health.json`](../.github/repository-health.json). The
human-readable result is written to the GitHub Step Summary. The full structured
result is uploaded as `repository-health-report.json`, even when a check fails.
All checks continue where safely possible so a run reports every finding at once.

## Quiet admission and propagation

All live CLI invocations use propagation admission by default; the explicit
`--when-idle` flag is a compatible alias, not an opt-in security boundary.
Automatic live audits use `--when-idle --event schedule`. A delayed scheduled
invocation outside00:00–06:00 Europe/Berlin is recorded as
`DEFERRED_OUTSIDE_NIGHT_WINDOW` without executing the audit. Timezone-aware cron
tracks daylight saving time; GitHub can still delay/drop scheduled invocations
([official scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)).
The next nightly invocation retries; an integrator can explicitly dispatch after
finishing propagation. No automatic midnight completion or retry-time guarantee.

Admission checks all nine permanent heads, exact-SHA ancestry, same-repository
open governed propagation PRs and all nonterminal parent-qualification runs.
Active propagation yields `DEFERRED_PROPAGATION`, with every audit area `NOT_RUN`.
Recent unresolved hierarchy drift has a30-minute grace bridging the gap between
parent merge and the next PR/qualification. It is audited normally after that
grace; a PR/qualification older than2hours causes a fail-closed operational error
for inspection, not indefinite quiet deferral. API, permission, malformed or
incomplete responses remain errors. Fork PRs cannot suppress the audit.

Manual dispatch bypasses only the night window, never propagation admission.
An already synchronized hierarchy needs no arbitrary post-merge delay. The
integrator must not start another propagation while the Doctor is running.
Heads/activity are checked again after the actual audit: a newly started
propagation or changed head invalidates the result as
`DEFERRED_REPOSITORY_CHANGED`; independent security/permission/contract failures
are still reported as failures. This is read-only detection and result binding,
not an atomic lock against an unrelated actor who ignores integration protocol.

`DEFERRED_*` exits successfully as a scheduling decision to avoid a false
failure notification, but is NEVER a Doctor PASS. Acceptance consumers must
inspect the uploaded report and require `status=PASS`, `audit_executed=true`,
`admission.accepted=true` and their exact expected main/head set, not just the
GitHub workflow conclusion. A postponed/invalidated report cannot satisfy a gate.

The separate Branch synchronization push job uses exact-event-SHA-bound
`--observe-push`: normal immediate child lag is `PENDING_PROPAGATION`, not a
failed build and not accepted synchronization. Its default CLI, weekly schedule
and manual invocation remain strict and fail unresolved drift. API errors and
stale event identities still fail closed. No GitHub notification settings,
branch protection or required security gates are disabled.

## Security and failure behavior

The workflow has only read permissions. It never changes an Issue or label,
pushes or merges a branch, edits a ruleset, or attempts an automatic repair.
Actions use full commit pins and checkout does not persist credentials. A denied
security API is reported as `UNKNOWN_PERMISSION`, never as zero alerts, and makes
the run fail. CodeQL requires `security-events: read`, and Dependabot requires
`vulnerability-alerts: read`. GitHub's workflow token cannot read secret-scanning
alerts; that check therefore fails closed unless an approved read-only credential
with the dedicated permission is supplied as the repository Actions secret
`REPOSITORY_HEALTH_READ_TOKEN`. If that secret is absent, the workflow falls
back to `GITHUB_TOKEN` and fails closed rather than claiming zero alerts. Token
values are never reported.

Run the local contract checks with:

```bash
python3 tests/repository-health-test.py
python3 tools/repository-health/check.py --local --report repository-health-report.json
```

Run a live audit only with an appropriate read-only GitHub Actions token:

```bash
GITHUB_TOKEN='<read-only token>' python3 tools/repository-health/check.py
```

## Boundaries

The Doctor cannot see unpushed worktrees on other machines, sealed reports
outside this repository, hardware or Jenkins state, Vikunja credentials or its
private projection, or semantic product quality that has no corresponding test.
Those limitations are not presented as passing checks.
