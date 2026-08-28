# Branch governance

This fork uses permanent integration branches as an ownership hierarchy:

```text
main
├── android-main
│   ├── android-phone
│   └── android-vr
│       ├── android-vr-pico
│       └── android-vr-quest
├── apple-main
│   ├── apple-ios
│   └── apple-macos
├── linux-main
└── windows-main
```

The machine-readable source of truth is
[`../.github/branch-policy.json`](../.github/branch-policy.json). Changes to the
hierarchy, CI policy, and this document must be reviewed together.

## Required flow

Complete merges flow only from a direct parent into a child. A permanent child
must never be merged wholesale into its parent or a sibling. Reusable work found
on a child is moved into a focused `promote/<target-scope>/<name>` branch and
reviewed against the owning parent.

Ordinary work uses `<kind>/<target-scope>/<name>`, where `kind` is one of
`feature`, `fix`, `docs`, `refactor`, `test`, `tests`, or `ci`. Synchronization
and conflict-resolution branches use `sync/<target-scope>/<name>` or
`reconcile/<target-scope>/<name>`. The target scope is listed in
`.github/branch-policy.json`.

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
hierarchy levels, and child-to-parent merges. The `branch-sync` workflow opens a
pull request whenever a direct child is missing commits from its parent. It
enables auto-merge with a merge commit, but GitHub completes it only after every
required check and branch rule passes. Conflicts and failed target tests leave
the PR open for manual intervention; the workflow never uses an administrator
bypass.

Required status checks intentionally do not require a synchronization PR's head
branch to contain the latest target-branch commits. Requiring that would force a
forbidden child-to-parent merge before a parent-to-child synchronization could
complete. Pull-request workflows still test GitHub's merge result, and merge
conflicts, required checks, and every direction rule continue to fail closed.
Synchronization runs are serialized per parent branch, so simultaneous
Android, Apple, Linux, and Windows propagation cannot cancel or replace one
another.
If GitHub cannot compare a configured pair, it reports a warning and continues
checking the remaining children instead of aborting the complete sync run.
Synchronization PRs are created with the dedicated repository-installed GitHub
App, not with `GITHUB_TOKEN`. This lets the normal pull-request workflows run on
automatically opened PRs without granting write access to the workflow token.

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
3. Create the repository ruleset from
   `.github/rulesets/permanent-branches.json` using the GitHub Rulesets API or
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

## Branch synchronization GitHub App

Install the dedicated app only on this repository and grant it the minimum
repository permissions `Contents: read` and `Pull requests: read and write`.
Webhooks and organization or account permissions are not required. Configure:

- repository variable `BRANCH_SYNC_APP_CLIENT_ID` with the app client ID;
- Actions secret `BRANCH_SYNC_APP_PRIVATE_KEY` with one active app private key.

Rotate the private key in the GitHub App settings, update the Actions secret,
then revoke the old key. Never commit a private key or installation token.

## Local validation

Validate the policy and a branch pair without GitHub:

```bash
python3 tools/branch-policy/check.py validate
python3 tools/branch-policy/check.py check-pr \
  --base android-vr-pico \
  --head feature/android-pico/controller-mapping
python3 tests/branch-policy-test.py
```
