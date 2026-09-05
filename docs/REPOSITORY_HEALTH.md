# Repository Health Doctor

The Repository Health Doctor is a fail-closed, read-only audit of repository
governance. It runs every day and can be dispatched manually. Pull requests run
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
