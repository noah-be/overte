# Branch governance

This fork uses permanent integration branches as an ownership hierarchy:

```text
main
├── android-main
│   ├── android-phone
│   └── android-vr
│       └── android-vr-pico
├── apple-main
│   └── apple-ios
├── linux-main
└── windows-main
```

The machine-readable source of truth is
[`../.github/branch-policy.json`](../.github/branch-policy.json). Changes to the
hierarchy, CI policy, and this document must be reviewed together.

`android-vr-quest` and `apple-macos` are deliberately outside the active
hierarchy. They are kept as frozen historical branches under
`.github/rulesets/archived-branches.json`: updates, force-pushes, and deletion
are prohibited, and the synchronization bot does not enumerate them.

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
feature/linux/wayland-input             -> linux-main
feature/windows/desktop-adapter         -> windows-main
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

When a direct synchronization conflicts, a same-repository reconciliation PR
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

Required status checks intentionally do not require a direct permanent-parent
synchronization PR's head branch to contain the latest target-branch commits.
Requiring that would force a forbidden child-to-parent merge before a
parent-to-child synchronization could complete. An attested reconciliation is
different: its head must directly merge the current target and current parent.
Pull-request workflows still test GitHub's merge result, and merge conflicts,
required checks, and every direction rule continue to fail closed.
Drift-detection runs are serialized per parent branch, so simultaneous Android,
Apple, Linux, and Windows checks cannot cancel or replace one another.
If GitHub cannot compare a configured pair, it reports a warning and continues
checking the remaining children instead of aborting the complete sync run.

The Android, Apple, and desktop target rulesets remain complementary and
mandatory. Their topology checks validate real Git ancestry and protected path
ownership; the general `branch-policy` check validates branch ownership and
direction. This policy does not replace any platform topology check.

## Enforcement bootstrap

The status check must exist on GitHub before it can be required. Activate the
system in this order:

1. Merge the policy, checker, tests, and workflows into `main`.
2. Confirm that the `Branch policy` workflow has produced the
   `branch-policy` check at least once.
3. Create the repository rulesets from
   `.github/rulesets/permanent-branches.json` and
   `.github/rulesets/archived-branches.json` using the GitHub Rulesets API or
   repository settings.
4. After `desktop-branch-topology` has run successfully on both desktop
   branches, create `.github/rulesets/desktop-branches.json` as a second
   mandatory ruleset.
5. Confirm with deliberately invalid draft PRs that `branch-policy` and the
   desktop topology check prevent merging.
6. Synchronize the policy commit from `main` down through every permanent
   branch.

With GitHub CLI authenticated for the repository, an administrator can create
the prepared ruleset with:

```bash
gh api --method POST "repos/{owner}/{repo}/rulesets" \
  --input .github/rulesets/permanent-branches.json
```

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
