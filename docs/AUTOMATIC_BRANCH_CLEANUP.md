# Automatic branch cleanup

The `Automatic branch cleanup` GitHub Actions workflow retires fully integrated
working branches in `noah-be/overte`. It runs on GitHub-hosted Ubuntu runners and
continues operating while the maintainer's computers are switched off.

There is no branch-age requirement or waiting period. A merged pull request wakes
the cleanup immediately; a five-minute schedule catches other eligible branches
and retries work that was previously held. GitHub may delay scheduled workflows,
so this is a detection interval, not a five-minute completion guarantee.

GitHub's native `delete_branch_on_merge` setting remains disabled. All automated
deletions must pass the cleanup's checks and backup sequence.

## What can be deleted

The workflow uses the trusted configuration in
[`.github/branch-cleanup.json`](../.github/branch-cleanup.json). Its repository name
and numeric repository ID must both match this fork. The nine permanent branches
are always excluded:

- `main`
- `android-main`, `android-phone`, `android-vr`, `android-vr-pico`
- `apple-main`, `apple-ios`
- `linux-main`, `windows-main`

A working branch must be fully contained in a permanent branch. A merged PR by
itself is insufficient: later commits on its source branch must also be
integrated. Protected branches, configuration holds, PR keep requests, open PR
relationships, active GitHub Actions runs on the candidate or its target, and deployment or release references
prevent deletion. The cleanup also checks open issue descriptions, comments on
explicitly active issues, and the GitHub workflow YAML files at the nine permanent
branch commits for branch references. Workflow reads use those exact commits;
plain and URL-encoded branch names are recognized. Even a historical mention in a
workflow may conservatively keep a branch. This does not inspect every source
file or external service configuration. Dynamically selected cross-branch consumers
must reserve their source branches with a policy hold or `keep-branch` label.
Unavailable or ambiguous evidence stops
the affected cleanup instead of being interpreted as inactivity.

Immediately before deletion, the implementation rechecks the current evidence
and branch SHA. The Git deletion uses an explicit expected SHA, so a branch that
has received another push cannot be deleted using an older plan.

## Keep a working branch

There are two ways to record that a branch must remain available on GitHub:

1. Add its exact name and a reason to the `holds` object in
   `.github/branch-cleanup.json` through a reviewed PR to `main`.
2. Apply the `keep-branch` label to a PR from that branch. The cleanup also honors
   this label on closed and merged PRs.

An open PR is itself a hold. Remove an explicit hold or keep label only after the
branch's ongoing work has finished. Holds do not expire automatically.

The configuration initially preserves the nine branches identified during the
2026-09-10 local-work review. The reason `ongoing_local_work_review` records that
decision without publishing local workspace paths or machine information.

**GitHub cannot inspect unpublished commits or worktrees on an offline computer.**
Before continuing local work on a remote branch that is already fully integrated,
record a hold or keep an associated PR open. A local checkout alone cannot reserve
that remote branch. This is the deliberate boundary of operating entirely on
GitHub; the workflow has no Jenkins, local daemon, or self-hosted runner dependency.

## Backups and recovery

Before deleting any planned branches, the workflow:

1. Creates a self-contained `recovery.bundle` with a manifest and SHA-256 checksums.
2. Verifies that the bundle can restore the recorded Git history into an empty
   repository.
3. Uploads the verified files as
   `branch-cleanup-backup-<run-id>-<run-attempt>` and checks the artifact receipt.
4. Creates and verifies annotated recovery tags under
   `archive/merged/<full-commit-SHA>` before deleting their corresponding branch
   references.

The existing `archive/**` rules protect recovery tags against deletion and
replacement. These tags have no expiry and are excluded from branch cleanup.
The downloadable bundle artifact is retained for 30 days; reports are retained
for 14 days. The plan, manifest, and tag metadata identify the original branches
and commits. A backup upload failure prevents deletion.

To recover a branch, first read the run's report or the relevant recovery tag and
confirm its original name and full commit SHA. Creating the branch again points
to that same commit; it does not alter an existing branch. For example, after
substituting the verified values:

```bash
BRANCH='feature/main/example'
SHA='the-verified-40-character-commit-SHA'
test "$(gh api repos/noah-be/overte --jq .full_name)" = noah-be/overte
gh api --method POST repos/noah-be/overte/git/refs \
  -f ref="refs/heads/$BRANCH" -f sha="$SHA"
```

Add a hold before restoring a fully integrated branch that must remain available;
otherwise a later cleanup can retire it again. The downloaded bundle also permits
local recovery if the normal fetch path is unavailable. Verify `SHA256SUMS` before
using that copy.

## Reports and manual runs

The Actions run contains a `branch-cleanup-report-<run-id>-<run-attempt>` artifact
with the plan and outcome. Retained branches carry reasons; successful deletions
record their recovery information. Failures remain visible in the workflow run.

Manual dispatch defaults to `report`. It performs the assessment without creating
recovery tags or deleting branches:

```bash
gh workflow run branch-cleanup.yml --repo noah-be/overte -f mode=report
```

Explicit `mode=apply` performs the same backup and deletion sequence used by the
automatic triggers. Report mode is not a pause switch for separately scheduled
runs; to keep a particular branch, use a configuration hold or PR keep label.

The workflow checks out only cleanup code and policy from trusted `main`, with
checkout credentials disabled. Candidate branch code and artifacts are never
executed. Concurrent cleanup runs share one concurrency group. A full Git backup
is made only when there are eligible candidates, avoiding a complete repository
download on every scheduled check.

The schedule and event behavior follow GitHub's
[documented workflow triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
