# Dormant authenticated producer API adapter

[`producer_api.py`](../tools/test-evidence/producer_api.py) connects the dormant
[producer protocol](../tools/test-evidence/producer.py) to read-only GitHub facts.
It has no workflow entrypoint, dispatch, retry, concurrency lease, automatic
fallback, check publication or metadata-skip capability. Existing checks keep
their current behavior. Successful execution jobs alone are never reusable proof.

## Trusted controller interface

`Adapter.capture(number, plan, policy, now=...)` returns a `Snapshot` containing
the independently observed exact current PR binding, current references,
authenticated observations, source chains, explicitly classified other original
candidates and inventory gaps.
`Adapter.verify(number, plan, policy, contexts, clock=...)` also reads and verifies
the newest aggregate and its complete selected inner receipts. It returns the
original qualification time and expiry without extending either.

The separate `Adapter.capture_integrated(push_run_id, plan, policy, now=...)`
and `Adapter.verify_integrated(push_run_id, plan, policy, contexts, clock=...)`
look up the original PR source after a normal merge into the exact current
protected target. The snapshot binding and inner context still identify the
original tested synthetic PR commit. The result returns independently observed
`integration` facts separately; it never changes the receipt's candidate to the
later merge commit or authorizes a sync edge.

`AdapterPolicy` supplies a reviewed protocol `Policy`, the exact outer workflow
ID/path, complete approved workflow-generation tuples, exact early publisher/owner
job names and a reserved final publisher prefix. A trusted controller must load
these from its reviewed checkout. The
adapter accepts no candidate policy file or JSON-to-authenticated-facts shortcut.
The injectable API object is an offline-test/trusted-controller boundary, not an
authentication mechanism for untrusted callers. `SharedContext` must separately
come from trusted immutable Git and actual runtime capture; receipt JSON cannot
construct it.

The open contract supports same-fork PRs whose approved
`.github/workflows/repository-checks.yml` calls the local reusable
`.github/workflows/project-tests.yml`. Foreign heads, other trigger/source
contracts and unsupported owners remain unavailable. Each approved generation
binds the complete ordinary-file tuple of `project-tests.yml`,
`parent-qualification.yml`, `sync-validation.yml` and `repository-checks.yml`.
An independently allowed file cannot authorize an unreviewed mixed tuple.
Legacy package generations without complete producer artifacts remain unusable
for this protocol even if their workflow tuple is otherwise approved.

## Independently authenticated facts

The adapter reads repository identity; live PR base/head/merge; current base,
head, merge and default-branch refs; and the exact immutable merge tree and
ordered parents. Merge identity comes from the supported
`commits/refs/pull/<number>/merge` endpoint and an independent immutable Git commit
read, without relying on the PR `merge_commit_sha` payload field. Branch refs
are URI-escaped inside the fixed fork;
the PR number and all commit IDs are independently validated. It checks these
facts before and after work. Actions `head_sha` is
the PR branch head, so it cannot identify the tested synthetic merge or reusable
workflow source. The API's `referenced_workflows` must independently identify the
original local producer merge/ref. Its immutable Git tree must contain one exact
approved complete caller/producer generation and match the current candidate.
The descriptor cannot supply a missing original source chain.

Run enumeration filters only the exact PR head and approved caller workflow;
it includes every status. Every run considered for reuse is resolved to its
latest API attempt and complete current-attempt job inventory. Only attempt 1
is admissible. Failed-only
retries can expose new job IDs and attempt numbers with original successful
timestamps; those snapshots do not authenticate original execution. A later
attempt makes the source unavailable, rather than borrowing attempt 1.
Check-suite/check-run APIs independently
bind repository, Actions app and job ownership. Ambiguous names, unclassified
runs, changed inventories, mixed reruns and tied authority prevent reuse. A newer
pending, failed or cancelled run for the current candidate never inherits an
older green. A different original merge with the same branch head is excluded
only after validating its original reusable source, complete approved workflow
tuple, ordered parents, same head, repository/app authority and first attempt.
`Snapshot.other_candidates` records its independently read merge/tree/parents.
None of its artifacts, results or runtime are reused. An unknown source, missing
reference, malformed parent, wrong app or rerun still makes the inventory
unavailable; a claimed old context is not a filtering instruction.

Artifact inventory must be complete, the run/attempt-specific name unique, and
detail metadata unchanged. The fixed fork GET endpoint supplies the bounded raw
ZIP. Its size and SHA256 must equal the independently read artifact API metadata.
The protocol then validates its exact single-member envelope, original lifetime,
descriptor, all selected successful current-attempt jobs and inner source/runtime
receipts. Missing/pending/failing/skipped owners never satisfy a selected result.
Verification takes another complete authority snapshot before returning.

The final publisher is a distinct native Actions job named by the exact trusted
prefix followed by the lowercase 64-character SHA256 of the complete canonical
shared execution receipt, including `receipt_digest`. Its name, status, result
and time window must agree with its independently read native check run, under
the same Actions app, suite, run and original attempt. Missing, malformed,
duplicate or conflicting reserved names cannot supply proof. The initial and
final authenticated commitment must remain equal; re-signing a changed receipt
or replacing its artifact does not replace the native commitment. The terminal
aggregate currently supports exactly one shared owner. Early descriptors remain
usable for pending-authority diagnostics without a final publisher.

## Integrated source lookup

The integrated route authenticates an actual first-attempt `push` run from the
fixed repository and registered `parent-qualification.yml` workflow for `main`,
`android-main`, `android-vr` or `apple-main`, or `project-tests.yml` for
`android-phone`, `android-vr-pico` or `apple-ios`. The workflow ID/path, current
protected branch API, independent Git ref, immutable commit, check suite and
Actions app must agree. An old tip, dispatch, PR event, foreign run, failed push
or rerun is unavailable. These facts and the current default-branch ref are
bookended around source capture and aggregate verification.
The actual current consumer push may still be queued or in progress with no
conclusion, or may be completed successfully. It is authenticated provenance,
not evidence that its selected tests passed. Only the independent original
producer can supply completed successful proof; this route does not require a
consumer to finish before looking up that source.

The complete commit-to-PR API inventory must authenticate exactly one actual
merged same-fork PR introducing that protected push. Every returned association
is independently read in full, with matching summary/full ID, state, base and
head identity. Known open or other merged downstream associations are classified
and bookended without supplying source authority. Unknown or contradictory
associations and multiple introducers remain unavailable.
The closed introducing PR's actual merge SHA,
base/head commits and target must match the immutable merge and its two ordered
parents. Squash, rebase, ambiguous introducers and incomplete inventories are
unsupported. Neither the deleted topic ref nor the former live PR merge ref is
requested. Closed PR runs can have an empty API `pull_requests` array; only this
separate route accepts it after authenticating that independent merged-PR chain.
The open route still requires its original API association.

The existing adapter reads remain pinned to REST version `2026-03-10`. That
version removed `merge_commit_sha` from PR summaries and full PR responses.
Only the integrated route's full PR read explicitly uses the supported
`2022-11-28` version to authenticate the actual merged SHA; it has the same fixed
fork GET, deadline, byte limit and strict JSON boundary. No summary merge field
is assumed, and there is no silent version fallback. A missing retained field,
unsupported API version or summary/full conflict prevents lookup. GitHub's
[breaking changes](https://docs.github.com/en/rest/about-the-rest-api/breaking-changes)
and [API version contract](https://docs.github.com/en/rest/about-the-rest-api/api-versions)
document this endpoint-specific compatibility requirement.

Every original caller run for the exact PR head is still enumerated, including
queued, failed and cancelled runs. Its original `referenced_workflows` entry
must name this PR's exact `refs/pull/<number>/merge` and immutable source. Exactly
one distinct original candidate can match both the integrated tree and ordered
parents. A different known original candidate is classified without reading its
artifacts; an unknown candidate, rerun, mixed generation or changing inventory
prevents selection. A newer failure or pending source cannot borrow an older
green. Original qualification, descriptor and aggregate uploads, and the final
publisher must all finish before integration. Expiry remains the original
expiry. The controller must still supply the original synthetic candidate's
independent `SharedContext`; equal trees cannot alias it to the push SHA.

This is dormant provenance capture and original-proof verification. It does not
establish hosted isolation, qualify an Android owner, relax any of the seven
protected branches or six sync edges, or activate production reuse.

The default adapter issues GET requests only to `github.com` and
`noah-l-frank/overte` through a resolved system/hosted-toolcache `gh`. Candidate
CLI shadows are rejected. Each request has a 45-second deadline, bounded output
and drained private stderr; failures expose no token, signed redirect URL or
response body. JSON is limited to 2 MB; archives to the protocol's 2 MB bound.
Pagination is limited to ten pages of 100 records. Filtered run searches reaching
GitHub's 1,000-result cap remain unavailable. No partial inventory can select an
older result.

## Remaining activation dependencies

No current workflow publishes this protocol's early descriptor and terminal
aggregate. The staged shared execution artifact alone is diagnostic evidence,
not a complete aggregate or producer-authority claim. Before activation, a
trusted producer must publish the early exact descriptor before candidate work,
then a complete aggregate for every selected owner. Non-shared owners still need
their own complete inner validators. Complete approved source generations must
include that actual orchestration and source compatibility transition.

GitHub's artifact API authenticates a run, not the uploading job. The future
approved source must therefore prevent every untrusted candidate subprocess in
that run, including concurrent sibling jobs, from accessing artifact/runtime
credentials or modifying trusted reports. A publishing-job time window is not
an independent uploader identity. This adapter cannot prove isolation absent
from the reviewed producer/caller source. Producer/consumer concurrency and
fallback ownership also need separate implementation; this stage makes no
exactly-once claim and never treats a pending run as success.

The next implementation must reuse the existing Stage B supervisor, rather than
add another policy switch. Its current diagnostic does not qualify production:

1. Verify the complete materialized candidate against immutable Git blobs and
   modes, including import/discovery membership and unsupported aliases. Mount
   source, Git metadata and the effective dependency/toolchain profile read-only.
2. Run candidate code under a separate unprivileged host UID, attached through
   the existing pre-exec gate to a parent-owned cgroup. Keep publisher credentials,
   command files, reports and file descriptors inaccessible. Add independently
   owned cleanup for abrupt controller/service death.
3. Capture the actual effective runtime in protected probes before execution and
   after parent-issued subtree kill and kernel-confirmed `populated=0`. The
   candidate's receipt, exit code, self-digest or stdout cannot supply this proof.
   Retain exact source, selection, controller/runtime policy, attempt and expiry.
4. Publish an early descriptor, authenticated final receipt commitment and
   terminal aggregate from an exact approved
   reusable-PR source generation with no unisolated candidate sibling jobs.
   Require successful immutable uploads of the protected files; run-level artifact
   metadata and a publishing timestamp alone do not identify the uploader.
5. Qualify that source on the actual hosted image, then transfer ordinary shared
   ownership atomically. Preserve selected failures and fallback execution.
   Post-merge/child consumption also needs independent protected integration and
   input-closure checks. The separate integrated lookup authenticates original
   source provenance; a consumer still needs its own current-context admission.

The current adapter and protocol tests authenticate source/API facts only. They
do not establish Stage B post-kill isolation, authorize reuse or qualify a new VM.

## Offline verification

```bash
python3 tests/run-project-tests.py --suite producer-api
python3 tools/test-evidence/producer-test.py
python3 tools/test-evidence/registry-test.py
```

The `producer-api` suite also runs in the combined host profile. Fake paginated
API fixtures cover original source versus branch head, foreign/missing workflow
chains, mixed generations, app and artifact provenance, raw archive tampering,
latest queued/failed/tied attempts, missing or mixed selected jobs, final native
receipt commitments, actual runtime drift, changing live refs/inventories,
deleted-topic integrated lookup, exact merged PR/ordered-parent/protected-push
bookends, original expiry and bounded CLI failures. They run
no live request, product build, installation or dispatch.

The source contract follows the official [workflow-run API](https://docs.github.com/en/rest/actions/workflow-runs),
[job API](https://docs.github.com/en/rest/actions/workflow-jobs),
[artifact API](https://docs.github.com/en/rest/actions/artifacts),
[check-suite API](https://docs.github.com/en/rest/checks/suites) and
[PR event identity](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request).
The integrated contract additionally follows the official
[commit-to-PR association API](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit),
[merged PR fields](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request)
and [protected branch fields](https://docs.github.com/en/rest/branches/branches#get-a-branch).
