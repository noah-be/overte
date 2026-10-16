# Automatic branch cleanup

The `Automatic branch cleanup` GitHub Actions workflow retires fully integrated
working branches in `noah-l-frank/overte`. It runs on GitHub-hosted Ubuntu runners and
continues operating while the maintainer's computers are switched off.

There is no branch-age requirement or waiting period. A closed pull request wakes
the cleanup immediately. Manual runs and a fifteen-minute schedule catch other
eligible branches. Twelve fixed branch-push workflow completions can also retry
closed-PR heads after CI holds clear, covering all seven permanent branches and
their current parent, leaf and legacy platform owners. A trusted API preflight
checks the actual fork, workflow registration, immutable source, current target
head and exact current topic heads named by earlier closed PRs. It checks all
related active workflows, including native and manual work, before starting the
original cleanup plan. A hint is not integration evidence: full ancestry,
consumer, backup and deletion checks still run unchanged.

The completion route skips history adoption and its App token. Non-push,
unlisted, stale, still-active and hint-free notifications cannot start it.
There is no last-event election: an older callback delivered after a newer one
can perform the same fresh check. Once a branch is deleted, later callbacks
find no matching current head. No durable marker or deletion-decision cache is
introduced. Closed-PR, scheduled and manual assessments retain history adoption.
The existing mutex keeps `cancel-in-progress: false`, so a new notification does not
interrupt a running backup or deletion sequence. GitHub may delay scheduled
workflows; fifteen minutes is a detection interval, not a completion guarantee.
The schedule uses UTC minutes 7, 22, 37 and 52 to avoid the documented
top-of-hour scheduler load while retaining four assessments per hour. Confirm
scheduled operation with an actual `schedule`-event run; a successful closed-PR
assessment alone does not establish that the scheduler is firing.
Manual, dynamic and unlisted completion holds still rely on a later schedule or
manual assessment; the finite retry is not a delivery-time guarantee.

Every assessment reads current GitHub state. It does not authorize deletion from
a triggering event's result or execute candidate code or artifacts. If trusted
`main` advances before adoption or planning starts work, the stale checkout
reports `deferred`, a fixed reason and zero authorized candidates after fresh
ownership and ancestry checks confirm that both snapshots remain in current
`main`. The remaining planning/backup/deletion steps are skipped and a later
scheduled run reassesses
from current trusted code. This early deferral performs no adoption mutation or
branch deletion. Backup still requires an exact trusted checkout. During apply,
a freshly verified advance of `main` also defers before deletion. Unproven
staleness, incomplete integration, invalid backups, API failures and permission
errors remain failures; none grant deletion permission or a successful backup.

API errors include only fixed method, endpoint-family, HTTP-status and category
labels in the redacted report. Unknown HTTP causes remain unknown; raw response
bodies, stderr, signed URLs and credentials are not printed. Historical startup
failures caused by a disallowed action pin are distinct from these job outcomes;
the exact pinned action must be allowed by repository policy before a workflow
can start, even when its step is conditional.

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

When GitHub's active-run count disagrees with its returned rows during a job
transition, cleanup reloads all five active states up to four times, waiting
2, 5, and 10 seconds between attempts. Only a complete inventory is accepted;
newly visible activity still holds the branch. Persistently incomplete or
malformed responses stop both history integration and deletion.

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

## Immutable-read cache

`cleanup.py` provides an opt-in cache for repeated read-only assessments within
one trusted cleanup run and attempt. The automatic trusted job enables it with
`BRANCH_CLEANUP_IMMUTABLE_CACHE=1` for adoption, planning and apply; other callers
keep the uncached default.
No candidate source, downloaded artifact or other job may populate this cache.
It is not an `actions/cache` entry or a cross-run proof store.

Only two exact request forms are eligible: workflow-directory/file Contents
reads with a full commit SHA, and the cleanup's comparison of two full commit
SHAs. A new SHA, path or comparison pair requires a new read. Branch and tag
refs, repository ownership/settings, current branch protection, PRs, issues,
actions activity, releases, deployments, rules, artifact receipts and paginated
queries always remain fresh. Git object endpoints and local Git history are
not cached by this bounded preparation. All existing preflight, final assessment,
independent backup restore and exact deletion leases remain required.
Eligible responses return only the workflow path/type/blob/content/size or
comparison status/behind-count/merge-base SHA used by cleanup. Mutable user,
permission and URL metadata is discarded on both fresh reads and cache hits.

The fixed private directory is
`$RUNNER_TEMP/branch-cleanup-immutable-<run-id>-<attempt>`. Runner context, numeric
IDs, directory ownership/mode and unaliased ancestors are checked. Trusted
sticky temporary ancestors such as `/tmp` are supported when each descendant retains
trusted ownership; shared writable non-sticky ancestors remain rejected. Cache
directories themselves retain exact private mode `0700`. Entries use
private ordinary files, atomic replacement, an exact repository/request/run/
attempt/controller identity and a SHA-256 envelope digest. The digest detects
damage; it does not authenticate an untrusted writer. The workflow must retain
its existing trusted-code-only execution boundary. Workflow bodies additionally
retain their existing decoded Git blob identity check before reference scanning;
fixed system Git performs public object encoding without filters or object writes.
Corrupt, foreign, public, aliased or oversized entries cause a fresh read or a
closed failure. Failed requests and invalid fresh responses are never cached as
success. Limits are 2,048 entries, 64 MiB total and 3 MB per entry; saturation
uses fresh evidence. Entries and workflow bodies are not uploaded or logged.
If the hosted filesystem cannot establish the private cache during initialization,
the assessment keeps the original uncached API path. This optional initialization
fallback cannot mask API failures, invalid responses or changed safety evidence.

Retained adoption and cleanup reports include fixed `immutable_api_cache`
telemetry: `state` (`disabled`, `enabled` or `unavailable`), numeric `hits` and
`misses`, and `fresh_api_invocations` for `contents`, `compare` and `other`.
Counters cover that phase's adapter, include failed fresh invocation attempts,
and remain separate across processes. A paginated CLI invocation counts once;
these counters measure neither HTTP pages nor quota use. They contain no
endpoints, response headers, workflow contents or credentials and never affect
selection or deletion permission.
Direct archive downloads, writer/GraphQL operations and Git transport remain
outside these adapter counters.

For unchanged SHAs, the first workflow assessment still needs every unique
directory/content request. Later adoption/plan/apply assessments in that same
attempt can reuse those exact reads; mutable safety checks continue in full.
For example, 81 unchanged workflow requests across four passes become 81 initial
requests rather than 324. This is an arithmetic example, not a hosted measurement.
The offline fixture proves eight initial requests and zero additional requests
on the second pass; changing a permanent head refetches its new exact inputs.

Both cleanup reads and the independent Branch policy workflow currently use
the built-in `GITHUB_TOKEN`. GitHub documents its primary limit as
[1,000 requests per hour per repository](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#primary-rate-limit-for-github_token-in-github-actions),
with a higher Enterprise Cloud allowance and additional secondary limits. These
workflows can therefore compete for the repository's allowance. Cold reads,
changed SHAs, mutable checks, other runs and other workflows remain costs. This
cache does not guarantee sufficient quota and grants no permission when an API
request fails. The trusted automatic cleanup job opts in with
`BRANCH_CLEANUP_IMMUTABLE_CACHE=1`; other callers keep the uncached default.
Hosted cache availability and savings must be read from actual retained reports;
the offline fixtures do not establish live token quota or a measured API saving.

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

Expected concurrent changes use status `deferred` and a successful workflow step,
so they do not produce a failed-workflow notification. For a changed `main`
snapshot, fresh fork ownership and GitHub ancestry checks must independently
confirm that both snapshots remain in current `main`. An unrelated checkout,
rewind, missing proof or unavailable API still fails. Newly observed activity or
a changed candidate immediately before deletion also defers that attempt.

A deferral stops the remaining mutations, records its reason in the summary and
report, and leaves reassessment to closed-PR wake-ups and the bounded schedule. A
deferred plan publishes zero candidates and removes any stale plan; a deferred
history stage skips deletion planning. No `continue-on-error` masks errors.
Invalid policy, ownership/protection failures, incomplete activity inventories,
backup/restore errors and unexpected command/API failures remain red and retain
their normal failure notifications. Personal GitHub notification preferences are
unchanged.

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
