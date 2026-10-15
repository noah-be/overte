# Automatic branch cleanup

The `Automatic branch cleanup` GitHub Actions workflow retires fully integrated
working branches in `noah-l-frank/overte`. It runs on GitHub-hosted Ubuntu runners and
continues operating while the maintainer's computers are switched off.

There is no branch-age requirement or waiting period. A closed pull request wakes
the cleanup immediately. Completion of the listed CI workflows wakes it again,
including failed or cancelled runs, so branches held by running CI are reassessed
after that activity ends. Every wake-up evaluates current GitHub state; it does
not authorize deletion from the triggering run's result or execute its code or
artifacts. Cleanup itself is excluded from the explicit workflow-name list to
prevent recursive runs. Keep that list current when adding or renaming workflows,
including platform workflows maintained outside `main`. GitHub treats these
names as glob patterns; escape literal metacharacters such as the plus signs
in `Native C++ checks`. YAML quoting alone does not escape the pattern.

A five-minute schedule catches other eligible branches, retries work that was
previously held, and covers GitHub's workflow-chain depth limit. GitHub may delay
scheduled workflows, so this is a detection interval, not a five-minute
completion guarantee.

GitHub's native `delete_branch_on_merge` setting remains disabled. All automated
deletions must pass the cleanup's checks and backup sequence.

## What can be deleted

The workflow uses the trusted configuration in
[`.github/branch-cleanup.json`](../.github/branch-cleanup.json). Its repository name
and numeric repository ID must both match this fork. The seven permanent branches
are always excluded:

- `main`
- `android-main`, `android-phone`, `android-vr`, `android-vr-pico`
- `apple-main`, `apple-ios`

A working branch must be fully contained in a permanent branch. A merged PR by
itself is insufficient: later commits on its source branch must also be
integrated. Protected branches, configuration holds, PR keep requests, open PR
relationships, active GitHub Actions runs on the candidate or its target, and deployment references
prevent deletion. A release naming the candidate branch also prevents deletion.
A release referring to the exact candidate commit does not require the branch
when its existing release tag resolves to that same commit. Lightweight and
annotated tags are verified through read-only fork Git APIs, with bounded
annotation traversal. Missing or mismatched tag evidence keeps the release hold;
an unavailable API stops cleanup. Full ancestry and permanent-target
deletion/non-fast-forward protection remain mandatory. Releases, tags, and assets
are never changed by this assessment.
The cleanup also checks open issue descriptions, comments on
explicitly active issues, and the GitHub workflow YAML files at the seven permanent
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

The configuration originally held nine working branches during the 2026-09-10
local-work review; this was a historical hold list, not the permanent hierarchy.
The current `holds` object is authoritative. The reason
`ongoing_local_work_review` records unresolved local work without publishing
workspace paths or machine information.

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
4. Restores and verifies the bundle independently again, then rechecks current
   ownership, activity, ancestry, and permanent-target protection before deleting
   the exact recorded branch heads.

Automatic cleanup creates no tags and does not require archive-tag rules. The
integrated commits remain reachable through their protected permanent target.
Existing historical tags are unchanged. The downloadable bundle artifact is
retained for 30 days; reports are retained for 14 days. The plan and manifest
identify the original branches and commits. A backup upload failure prevents
deletion. Download the recovery artifact during its retention period if you need
to retain the branch-name mapping for longer.

## Work adopted through another history

The same cleanup workflow assesses closed working PRs whose exact source heads
are not ancestors of their permanent targets. It does not interpret closure,
age, supersession, or a matching commit message as evidence that work was adopted.
An open or draft PR, a changed source head, keep request, consumer reference or
active CI retains the branch. Branches without a completed same-fork PR are not
automatically considered.

For an eligible source, `tools/branch-cleanup/adoption.py` computes a normal
`git merge-tree --write-tree` against the exact current permanent target. Only a
conflict-free result whose complete Git tree equals the existing target tree is
accepted. This includes file contents, modes, symlinks, additions and deletions.
No forced merge strategy or semantic similarity judgment is used. The temporary
bare repository never checks out candidate code and disables hooks, global Git
configuration and custom external merge drivers.

The automation opens a `fix/<scope>/adopted-history-pr-<number>-<sha>` PR. Its
commit has the permanent target and original source as parents and retains the
exact target tree. Original commits remain reachable after the ordinary PR merge.
The existing branch cleanup can then retire both temporary branches through its
normal ancestry checks and verified backup sequence, without archive tags.

History PRs run the normal required GitHub checks. Later cleanup wake-ups merge
them only when GitHub reports them mergeable and all required protections remain
active and strict. Before merging, it independently reads successful checks from
their required GitHub Apps on the exact head and GitHub's current merge/review
decision, without relying on the writing App's privileges. The standard PR merge
API enforces the server-side rules; the automation grants no approvals, writes no check results,
and bypasses no checks. A fresh tree proof and activity/consumer checks precede
merging, with exact head matching. A target advance is handled by a fast-forward
refresh of the history branch followed by fresh CI. Closing an automated PR or
adding `keep-branch` stops its automatic integration. At most one history PR is
created, refreshed or merged per cleanup run. Introduced commit messages with
issue-closing references and PRs with GitHub-reported closing issue links are
held for review, preventing history integration from completing issues.

Conflicts and merges that would change the tree are reported for review and
retain the source. Negative verdicts may be reused from retained report artifacts
only for the exact source, target, PR and implementation version. A cached result
can only defer work; positive proofs always run again before any integration.
Unchanged negative verdicts remain in subsequent reports, including runs with
activity holds. Complete Git objects are fetched only for uncached eligible
source/target pairs; this avoids lazy object-fetch failures during real merges.

### GitHub App configuration

The existing **Overte Branch Synchronization** App supplies an installation token
scoped to `noah-l-frank/overte`, with **Contents: read and write** and
**Pull requests: read and write**. It needs no administration, issue-completion,
check-writing or branch-protection bypass permission. Unlike `GITHUB_TOKEN`, the
App's branch and PR writes trigger the normal CI workflows.

Configure the repository variable `BRANCH_SYNC_APP_CLIENT_ID` and repository
secret `BRANCH_SYNC_APP_PRIVATE_KEY`. The private key must never appear in an
issue, PR, log or repository file. A pinned official token action creates and
revokes the short-lived, repository-scoped token. With no App configuration the
new stage reports findings only; ordinary integrated-branch deletion continues.
Manual `mode=report` never mints an App token or writes commits, branches or PRs.
Only the cleanup workflow at trusted fork `main` can perform these operations.

## Branch recovery

To recover a branch, first read the retained run report or backup manifest and
confirm its original name and full commit SHA. Creating the branch again points
to that same commit; it does not alter an existing branch. For example, after
substituting the verified values:

```bash
BRANCH='feature/main/example'
SHA='the-verified-40-character-commit-SHA'
test "$(gh api repos/noah-l-frank/overte --jq .full_name)" = noah-l-frank/overte
gh api --method POST repos/noah-l-frank/overte/git/refs \
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
backups or deleting branches:

```bash
gh workflow run branch-cleanup.yml --repo noah-l-frank/overte -f mode=report
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
