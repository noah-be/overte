# Branch governance

This fork uses permanent integration branches as an ownership hierarchy:

<!-- generated:branch-table:start -->
| Permanent branch | Parent | Task scope |
| --- | --- | --- |
| `main` | — | `main` |
| `android-main` | `main` | `android` |
| `android-phone` | `android-main` | `android-phone` |
| `android-vr` | `android-main` | `android-vr` |
| `android-vr-pico` | `android-vr` | `android-pico` |
| `apple-main` | `main` | `apple` |
| `apple-ios` | `apple-main` | `ios` |
<!-- generated:branch-table:end -->

The machine-readable source of truth is
[`../.github/branch-policy.json`](../.github/branch-policy.json). Changes to the
hierarchy and CI policy must be reviewed together. The table above is generated
from that policy. After an intentional policy change, run
`python3 tools/repository-policy/check.py --write`; the read-only check rejects
stale displays and inconsistent cleanup, synchronization, or ruleset topology.

The seven permanent branches have six parent-to-child edges. Linux and Windows
implementation, tests, desktop adapters, and target matrices belong on `main`.
The retired desktop, Quest, and macOS branch names do not designate active
synchronization targets.

## Required flow

Complete merges flow only from a direct parent into a child. A permanent child
must never be merged wholesale into its parent or a sibling. Reusable work found
on a child is moved into a focused `promote/<target-scope>/<name>` branch and
reviewed against the owning parent.

Ordinary work uses `<kind>/<target-scope>/<name>`, where `kind` is one of
`feature`, `fix`, `docs`, `refactor`, `test`, `tests`, `ci`, or `sync`.
Conflict-resolution branches use the stricter
`reconcile/<target-scope>/<name>` form. The target scope is listed in
`.github/branch-policy.json`, and a reconciliation name is valid only for a
permanent branch with a direct permanent parent.

Examples:

```text
feature/android-pico/controller-mapping -> android-vr-pico
fix/android-vr/openxr-logging           -> android-vr
promote/apple/qt-event-fix              -> apple-main
feature/main/wayland-input              -> main
feature/main/windows-desktop-adapter    -> main
android-vr                              -> android-vr-pico
sync/android-pico/android-vr-refresh    -> android-vr-pico
```

The `branch-policy` workflow rejects wrong scopes, sibling merges, skipped
hierarchy levels, and child-to-parent merges. The `branch-sync` workflow is a
read-only drift detector: it reports whenever a direct child is missing commits
from its parent, but it does not create pull requests, write repository content,
or enable auto-merge. A maintainer creates the required synchronization pull
request, and conflicts or failed target tests remain visible for manual
resolution without an administrator bypass.

Privileged policy and synchronization files normally change only through a
same-repository pull request to `main`. A direct downstream synchronization may
carry those parent-owned files into its immediate child only when the permanent
parent branch itself is the pull-request head. The workflow requires that head
to be the current remote parent SHA.

When a direct synchronization conflicts or cannot satisfy the target's strict
up-to-date requirement, a same-repository reconciliation PR
may carry the privileged paths only after a separate fail-closed attestation.
The trusted checker reads the current base and its configured direct parent's
SHA from the GitHub API, requires the reconciliation head to be the direct merge
of those two exact commits, and verifies both ancestry comparisons. It then
compares every privileged path in the complete head and parent trees, including
existence, mode, object type, and blob SHA. A missing, added, changed, deleted,
or differently typed entry fails the check. Both permanent refs are read again
after the comparisons, so a moving base or parent also fails closed.

The attestation code is checked out only from the repository default branch.
It reads PR metadata and Git objects through the API; it never checks out or
executes PR-owned scripts or workflows. Its workflow permissions remain
`contents: read` and `pull-requests: read`. Forks, stale snapshots, wrong
scopes, skipped hierarchy levels, child-to-parent flows, sibling flows, and
ordinary `sync/*` topics cannot use this exception.

Required status checks use strict mode in the permanent, Android and Apple
ruleset manifests; the September 2026 rollout inspection confirmed the same
requirement in the live rulesets. A direct parent PR may therefore be considered
out of date when its child contains commits absent from that parent. Do not
disable strict checks or merge a permanent child back into its parent.

Use an attested `reconcile/<child-scope>/<name>` branch based on the current
child, with the current direct parent merged into it. This produces an
up-to-date candidate while preserving the parent-to-child direction. Its exact
head, ancestry, privileged paths and target checks must satisfy the existing
reconciliation contract. Direct parent PRs remain valid only when all applicable
rules allow them. Pull-request workflows test GitHub's merge result, and merge
conflicts, required checks and direction rules continue to fail closed.
Drift-detection runs are serialized per parent branch, so simultaneous Android,
Apple, and shared-parent checks cannot cancel or replace one another.
If GitHub cannot compare a configured pair, it reports a warning and continues
checking the remaining children instead of aborting the complete sync run.

The Android and Apple target rulesets remain complementary and mandatory.
Their topology checks validate real Git ancestry and protected path ownership;
the general `branch-policy` check validates branch ownership and direction.
Desktop work uses the `main` rules and its applicable product checks.

## Enforcement bootstrap

The permanent, Android and Apple rulesets already exist. Preserve their required
contexts, strict checks and other protections while adding enforcement. A new
status check must run successfully before it becomes required.

Follow the [maintenance deployment sequence](REPOSITORY_MAINTENANCE.md#deployment):
stage trusted tools first, integrate and propagate workflow wiring, verify the
live success and failure paths, then update the existing ruleset by its freshly
resolved ID after retaining a rollback export. Read back the saved settings.
Do not create another ruleset merely because a versioned manifest exists, and
do not treat editing that manifest as a live settings change.

Do not add a routine administrator bypass. Emergency changes should still use a
pull request so the policy decision and CI result remain auditable.

## Local validation

Validate the policy and a branch pair without GitHub:

```bash
python3 tools/branch-policy/check.py validate
python3 tools/branch-policy/check.py check-pr \
  --base android-vr-pico \
  --head feature/android-pico/controller-mapping
python3 tests/branch-policy-test.py
```
