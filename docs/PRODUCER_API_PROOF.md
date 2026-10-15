# Dormant authenticated producer API adapter

[`producer_api.py`](../tools/test-evidence/producer_api.py) connects the dormant
[producer protocol](../tools/test-evidence/producer.py) to read-only GitHub facts.
It has no workflow entrypoint, dispatch, retry, concurrency lease, automatic
fallback, check publication or metadata-skip capability. Existing checks keep
their current behavior. Successful execution jobs alone are never reusable proof.

## Trusted controller interface

`Adapter.capture(number, plan, policy, now=...)` returns a `Snapshot` containing
the independently observed exact current PR binding, current references,
authenticated observations, source chains and explicit inventory gaps.
`Adapter.verify(number, plan, policy, contexts, clock=...)` also reads and verifies
the newest aggregate and its complete selected inner receipts. It returns the
original qualification time and expiry without extending either.

`AdapterPolicy` supplies a reviewed protocol `Policy`, the exact outer workflow
ID/path, complete approved workflow-generation tuples and exact publisher/owner
job names. A trusted controller must load these from its reviewed checkout. The
adapter accepts no candidate policy file or JSON-to-authenticated-facts shortcut.
The injectable API object is an offline-test/trusted-controller boundary, not an
authentication mechanism for untrusted callers. `SharedContext` must separately
come from trusted immutable Git and actual runtime capture; receipt JSON cannot
construct it.

This first contract supports open same-fork PRs whose approved
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
ordered parents. It checks these before and after work. Actions `head_sha` is
the PR branch head, so it cannot identify the tested synthetic merge or reusable
workflow source. The API's `referenced_workflows` must independently identify the
original local producer merge/ref. Its immutable Git tree must contain one exact
approved complete caller/producer generation and match the current candidate.
The descriptor cannot supply a missing original source chain.

Run enumeration filters only the exact PR head and approved caller workflow;
it includes every status. Every run is resolved to its latest API attempt and
complete current-attempt job inventory. Check-suite/check-run APIs independently
bind repository, Actions app and job ownership. Ambiguous names, unclassified
runs, changed inventories, mixed reruns and tied authority prevent reuse. A newer
pending, failed or cancelled run never inherits an older green. Older runs for a
different merge with the same branch head conservatively make this first adapter
unavailable; there is no implicit exclusion based on artifact claims.

Artifact inventory must be complete, the run/attempt-specific name unique, and
detail metadata unchanged. The fixed fork GET endpoint supplies the bounded raw
ZIP. Its size and SHA256 must equal the independently read artifact API metadata.
The protocol then validates its exact single-member envelope, original lifetime,
descriptor, all selected successful current-attempt jobs and inner source/runtime
receipts. Missing/pending/failing/skipped owners never satisfy a selected result.
Verification takes another complete authority snapshot before returning.

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

## Offline verification

```bash
python3 tests/run-project-tests.py --suite producer-api
python3 tools/test-evidence/producer-test.py
python3 tools/test-evidence/registry-test.py
```

The `producer-api` suite also runs in the combined host profile. Fake paginated
API fixtures cover original source versus branch head, foreign/missing workflow
chains, mixed generations, app and artifact provenance, raw archive tampering,
latest queued/failed/tied attempts, missing or mixed selected jobs, actual runtime
drift, changing live refs/inventories, expiry and bounded CLI failures. They run
no live request, product build, installation or dispatch.

The source contract follows the official [workflow-run API](https://docs.github.com/en/rest/actions/workflow-runs),
[job API](https://docs.github.com/en/rest/actions/workflow-jobs),
[artifact API](https://docs.github.com/en/rest/actions/artifacts),
[check-suite API](https://docs.github.com/en/rest/checks/suites) and
[PR event identity](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request).
