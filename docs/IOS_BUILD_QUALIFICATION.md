# iOS build qualification and installation provenance

A green host workflow is not a built IPA. A built IPA is not an installed app,
and a successful installation is not device acceptance. Keep these facts separate
and bind each result to its repository, exact source revision and producing run.

## Required merge qualification

The trusted tools under
[`tools/ios-build-qualification/`](../tools/ios-build-qualification/) are owned by
`main`. The product workflow is deployed to `apple-ios` from the canonical
[`workflow.yml`](../tools/ios-build-qualification/workflow.yml) template. The installed filename is
`.github/workflows/ios-build-qualification.yml`.

The independent required repository router compares the candidate's orchestration
with the template on the trusted default branch. A PR cannot replace the final
verifier or make it optional. The `enforceWorkflow` flag in
[the trusted configuration](../.github/ios-build-qualification.json) requires the
workflow to exist and match the template. The versioned Apple target ruleset also
requires `ios-device-build` alongside its existing topology check, with strict
up-to-date validation and GitHub Actions integration binding. An off flag or a
missing live required check is an incomplete deployment. Verify live settings;
the versioned files alone do not establish active protection.

The workflow runs for every PR targeting `apple-ios`, including parent merges and
retargeting. The router reads the exact synthetic merge candidate, checks its two
parents against the event, and never executes candidate code while selecting a
route. History-only PRs whose base, head and merge have the exact same Git tree
require no host, Qt or application build. This compares all tracked contents,
paths and modes, rather than trusting an empty file list from the PR API. The
final verifier independently checks the event, ordered parents and all three
tree identities again. The deployed legacy workflow obtains this metadata in
a fresh bare repository with a bounded, blob-filtered fetch from the fixed fork;
it never checks out or executes candidate code. Missing metadata fails the gate.
The result records `unchanged-tree`, no IPA and no new build claim.

In the legacy workflow, every other change except ordinary Markdown-only changes requires a full
physical-device E2E app build. New or unrecognized paths therefore receive full
coverage. Renamed source files, executable Markdown and symbolic links do not
qualify for the documentation exception.

## First host-only workflow deployment

The protected default-branch host controller and
[`ios-host-orchestration.json`](../.github/ios-host-orchestration.json) permit a
first `apple-ios` PR using the exact
[`host-workflow.yml`](../tools/ios-build-qualification/host-workflow.yml) generation.
The source guard and target list authorize that trial. They do not establish a
successful host run, application build, reusable artifact or device acceptance.
Legacy input selection and all existing required contexts remain unchanged.

The first lighter PR must start from reviewed source
`52f1cc38180e96cdfd8049a4be93517961ae7dbd`, tree
`f5b44d19b5c64c96bc3f73f72c51519dbfbf08a3`. Its complete immutable base/head/merge
inventories may differ only at `.github/workflows/ios-build-qualification.yml`,
replacing the exact legacy top workflow with the canonical host generation.
The other five generation sources remain exact. A changed source tree,
additional path, mode change or unrelated parent update requires fresh review;
it cannot use the one-file bootstrap exception.

That PR is the first end-to-end qualification. It requires the complete actual
same-run Ubuntu host launcher, a successful test step and the existing
`ios-device-build` final check, with fresh PR and branch-head API observations
before and after trusted selection and verification. The new host receipt
supports attempt 1 only. Missing, failed, cancelled, skipped or stale selected
host work blocks merging. The Qt source build, client build, build-history
lookup and IPA download/packaging are skipped for this exact workflow-only
transition. No previous run is reused and no IPA is attributed to the candidate.

Do not dispatch `ios-bootstrap` with every mode flag false to qualify this
transition: that existing dispatch selects simulator and unsigned-device app
builds. The one-file PR supplies its own required host evidence.

After deployment, the changed top workflow invalidates the older general
reader identity. Review the complete protected post-deployment source before
enabling broader app-neutral selection. In particular, npm-only app omissions
need applicable required Browser/S3 package owners with complete target wiring
and actual same-candidate results; this trial does not add that permission.

## Application build result verification

For a required build, host tests, Qt provisioning and the complete client build
must succeed. The final `ios-device-build` job uses `always()` and rejects missing,
failed, cancelled or skipped dependencies. It also reads the actual run/attempt's
job inventory and requires successful compiler, link verification, packaging and
artifact upload steps; an overall green reusable job alone is insufficient.

A failed-only retry of the qualifier can retain the successful producer jobs
from attempt 1 while the qualifier runs in attempt 2. The verifier requires the
five exact selected jobs to have unique positive API snapshot job IDs and one
consistent API snapshot attempt, belonging to the same run and PR head. A retry
may also create new job IDs and `run_attempt: 2` records carrying the unchanged
original successful step timestamps. The API attempt and job IDs alone do not
prove a new compilation. The verifier supports attempt-1 API snapshots with an
attempt-2 qualifier and same-attempt API snapshots; mixed snapshot attempts,
backwards ordering and other earlier-attempt combinations
fail. Every mandatory native step must still be `completed` with conclusion
`success`. Missing or nonterminal API step data fails even when the overall job
and package logs show success. A later API correction does not retroactively
change an earlier failed qualification.

The report preserves `runAttempt` as the qualifying attempt and separately
records `apiSnapshotRunAttempt`, `qualifierRunAttempt` and `apiSnapshotJobIds`.
It explicitly leaves `originalExecutionRunAttempt` and `originalExecutionJobIds`
null, with `originalExecutionIdentityVerification` set to
`not-observed-by-legacy-invocation`. The legacy invocation has no original
execution receipt to establish those fields; timestamps or a new API job ID
must not be substituted for that receipt. Preserve independently captured
original attempt-1 job/step receipts when comparing inherited retry snapshots.
Those separate observations do not retroactively rewrite historical reports.
The report never attributes a fresh compilation to a later API snapshot.
GitHub's [rerun documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
specifies reuse of the original event's `GITHUB_SHA` and `GITHUB_REF`. Preserve
the separate [job API](https://docs.github.com/en/rest/actions/workflow-jobs)
attempt records when examining a retry; same-source qualification and original
execution identity are different observations.
This compatibility change leaves the canonical workflow byte-identical and
does not trigger a rerun. Before a diagnosed failed-only retry, verify that the
run, PR head, compiled candidate and successful original producer jobs are
unchanged, and that all mandatory native steps have terminal successful API
results. A different candidate or unsuccessful producer cannot use this reuse.

The existing final invocation checks the inner IPA and manifest, as described
below. The pinned download action supplies extracted files; the verifier does
not receive the original artifact ZIP or its API artifact ID. Its report therefore explicitly marks additional
artifact-ID and original-ZIP-digest verification as
`not-observed-by-legacy-invocation`. Those fields must not be invented from the
producing attempt, IPA hash, filename or package logs. Independently retained
original ZIP bytes may be compared with their exact API artifact-ID/digest
receipt. An additional authenticated collector and independently checked ZIP
receipt require a separate trusted-template update and normal Main → Apple →
iOS propagation; the legacy verify step has no `GH_TOKEN` of its own. Changing
the canonical template also changes the mandatory candidate wiring check and
cannot transparently retrofit a frozen candidate or its old workflow snapshot.

The IPA must be unique and match the manifest's exact candidate SHA, workflow
build number, filename and SHA-256. The verifier checks the physical iPhoneOS
platform, arm64 Mach-O executable, Full Client product and dedicated E2E identity
inside the archive. It uploads a report with the exact source tree, PR parents,
run/attempt and IPA digest. Documentation-only qualification explicitly reports
`ipa: not-required`; it never claims that the new commit was compiled.

Qt, V8, Conan and compiler checkpoints use the existing validated restore paths.
`preserve_reusable_data` remains true. Matching reusable inputs can accelerate
compilation; an old IPA or a different source revision cannot satisfy this gate.
The required check runs before the merge. Strict branch protection forces a new
candidate when the base moves. A subsequent distributable build records its own
exact permanent-branch commit; do not describe an earlier PR merge SHA as that
later commit.

## Inspect before a manual build

The helper searches both `iOS bootstrap` and `iOS device build qualification`
history across iOS topics and PRs: run 686 on a prerelease topic already exposed the missing header later
reported by run 687 on `apple-ios`. It inspects the latest failed log and outputs
only bounded diagnostic categories, not raw logs or private device information.
The report declares a bounded window of 50 runs per workflow and records workflow
identity alongside run/attempt/build number, because build numbers are local to
each workflow. Before initial deployment, an unregistered qualification workflow
is explicit; an incomplete workflow inventory fails rather than silently omitting
it. Compilation failures and timeouts from either workflow require investigation.
Expired or unavailable logs are explicitly reported as uninspected with an unknown
diagnosis; they do not erase the recorded failure or claim a successful review.
The manual dispatch still requires a concrete diagnosis from retained evidence.

```bash
python3 tools/ios-build-qualification/history.py status \
  --output /tmp/overte-ios-build-status.json
```

The report distinguishes the latest workflow result, the latest successful Full
Client build with a matching artifact, artifact expiry, and whether the producing
revision matches current `apple-ios`. Available artifacts still say
`integrity: not-downloaded-or-verified`; download and verify them before install.
PR artifacts require their manifest to establish the synthetic merge revision.

For a user-authorized new build, inspect the failed run, repair the cause and
record the concrete diagnosis with the exact latest failed run ID:

```bash
python3 tools/ios-build-qualification/history.py dispatch \
  --reviewed-failure-run 36112850124 \
  --diagnosis 'The removed Android header is now included only in Android builds; the source-boundary regression passes.' \
  --output /tmp/overte-ios-build-dispatch.json
```

Use the current ID from the status report, not this historical example. An
unchanged failed source requires a separate `--retry-reason` describing the
repaired external prerequisite. The tool verifies the fork and current branch
before dispatch, selects `integrated=true`, preserves the workflow's checkpoint
restore defaults, and reads the new run back. If the branch races with dispatch,
the mismatch is reported rather than silently assigned to the reviewed source.
Do not blindly retry after a dispatch observation error: a run may already exist.

This is a review record, not proof that a natural-language diagnosis is correct.
The subsequent build and artifact checks remain mandatory. Automatic PR builds
retain a prior-failure report before compiling the changed candidate.

## Installed-device evidence

The local installation runner records the input IPA hash, producing build and
source SHA only after the signing/install/verification sequence succeeds. Its
receipt can be included in a local status report:

```bash
python3 tools/ios-build-qualification/history.py status \
  --installation-receipt "$HOME/.local/state/overte-ipad-install/bundle-identity.json" \
  --output /tmp/overte-ios-build-and-installation-status.json
```

The result labels this as a supplied historical receipt and says whether it
matches the current source. It does not claim a fresh device query or authenticate
an arbitrary local file. Do not infer CI build 669, 687 or another producing run
from app version `0.1.0` / app build `1`; those values are reused by the package.
Keep signing material, device selectors and raw installation logs outside Git.

## Staged enforcement

1. Integrate trusted tools, template, tests and this guide on `main`, keeping the
   rollout flag off. Preserve all existing required checks.
2. Propagate the parent-owned foundation through `apple-main` to `apple-ios` and
   install the canonical workflow through a normal product PR.
3. Verify a real application-build success and a documentation-only result.
   Exercise negative cases locally: skipped compilation, missing IPA, wrong SHA,
   stale attempt, changed orchestration and incomplete installation provenance.
4. Turn `enforceWorkflow` on in the trusted default-branch configuration through a
   normal PR. Verify the required repository router validates the product workflow.
5. Export the current Apple target ruleset for rollback, add `ios-device-build`
   with GitHub Actions integration ID 15368 to its existing required checks,
   preserve strict mode and every other rule, then read the live settings back.
   Keep its versioned manifest consistent. No new duplicate ruleset or admin bypass.

Local tests or a versioned ruleset file alone do not establish live enforcement.
The active plan records actual rollout PRs, runs and the final read-back evidence.

## Regression checks

```bash
python3 tests/ios-build-qualification-test.py
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

These tests cover routing and evidence failures; the real iOS compiler run is a
separate requirement. Passing them does not claim physical-device acceptance.
