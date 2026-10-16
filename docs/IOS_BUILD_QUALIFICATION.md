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

The first lighter PR must start from a protected base with tree
`f5b44d19b5c64c96bc3f73f72c51519dbfbf08a3`, reviewed at source
`52f1cc38180e96cdfd8049a4be93517961ae7dbd`. History-only merges can retain that
same complete tree; the event and fresh branch observations still bind their
actual current commit identities. Its complete immutable base/head/merge
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

PR #1300 completed this deployment without a Qt or client build. Its protected
merge `2fc894a0605103843b36653f250f854714a963ee` has tree
`94566f00d4cc1665d98cb570d285f5f80b7bd0a7`. The general reader anchor now uses
that protected source: its only tree change from the older anchor is the exact
reviewed top workflow. Already reviewed independent CI and documentation paths
can therefore omit the app build while retaining fresh mandatory iOS host
checks. Both input trees must still match this reader boundary; new application
readers invalidate the exception even for a later CI-only change.

The own iOS host run also has an independent, narrower negative dependency
boundary in `host.py`. Exactly 142 reviewed CI paths may change while both the
protected base and merge candidate retain the complete reviewed complement of
11,168 ordinary Git entries, including historical child differences, test
discovery, imports, helpers, product sources, consumed documentation and modes.
Unknown paths, new discovery members, native scan inputs, missing files, mode
changes, symbolic links and gitlinks invalidate this boundary. There is no
generic Markdown, tools or tests exemption. The app input selector must separately
require no application build before the host omission can apply.

For this reviewed CI-only route, the separate iOS host, Qt and client jobs are
skipped. The final verifier independently recomputes the selection and requires
those exact skipped results. Its evidence records `iosHostRequired: false`, no
host producer and no IPA; it does not claim a passing test execution or reusable
test receipt. Required shared CI still runs its relevant owners, including the
changed control-plane launcher. A changed iOS reader complement conservatively
restores the complete own iOS host run until that graph is reviewed again.

Five additional finite CI paths cover `npm_consumers.py`, its two CJS probes and
the paired `workflows/npm-consumers/` Browser/repository templates. The exact
staged `tools/repository-checks/workflows/sync-ci-selection.yml` template is also
independent CI: the protected iOS launcher does not import or discover it, and
ordinary YAML is outside its repository-wide native source scan. The template
is absent from the protected reader tree, so admitting this one path leaves both
reviewed complement identities unchanged. The three exact dormant
`tools/repository-checks/workflows/metadata-edits/repository-checks.yml` and
`sync-test-reuse.yml` and `codeql.yml` templates have the same negative reader proof: none is
present in the protected tree, imported by the launcher or included in native
source discovery. They do not activate metadata-only routing. Sibling paths and
executable YAML remain conservative inputs.

Twelve more exact ordinary CI sources cover `.github/android-owner-transfer.json`,
`tests/android-owner-transfer-test.py`, `tools/repository-checks/android_handoff.py`
and nine staged files under `tools/repository-checks/workflows/android-owned/`:
`android-required.yml`, `project-tests.yml`, `repository-checks.yml`,
`handoff/.github/workflows/android-tests.yml`, `handoff/.github/workflows/android-vr-tests.yml`,
`handoff/android/common/tests/android-workflow-contract-test.py`,
`handoff/android/common/tests/ci/test_ci_contract.py`,
`handoff/android/common/tests/ci/validate_ci_contract.py`, and
`handoff/android/phone/tests/phone-release-metadata-test.py`.
None exists in the protected reader tree, is imported by its launcher or belongs
to either discovered iOS test directory. The native source scan excludes their
JSON, YAML and Python suffixes. Both immutable reader complements therefore keep
their existing identities. This admits only their ordinary `100644` staging
sources; it does not exempt the executable Android product targets, unknown
siblings, mode changes or symbolic links, and does not activate the staged owner.

Ten exact sandbox CI controls are separately reviewed:
`.github/shared-sandbox.json`, `.github/workflows/shared-sandbox-host-diagnostic.yml`,
`tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml`, and
`tools/test-evidence/sandbox.py`, `sandbox-test.py`, `sandbox_host.py`,
`sandbox-host-test.py`, `sandbox_host_fixture.py`, `sandbox_probe.py`, and
`sandbox_shared.py`.
All ten are absent from the protected iOS tree. Its fixed launcher and imports
neither execute nor read them, its two discovery directories do not include
these paths, and its repository-wide native scan excludes their JSON, YAML and
Python suffixes. Both existing immutable complement identities therefore remain
unchanged. Only ordinary `100644` sources are admitted; executable modes,
symbolic links, new siblings and native scanner inputs remain conservative.
The required shared CI owners still validate these controls. This path admission
neither runs the privileged manual diagnostic nor qualifies sandbox execution.

The exact ordinary `tools/test-evidence/producer_workflow.py` and
`tools/repository-checks/workflows/producers/protected-project-tests.yml` sources
are also outside both protected iOS reader graphs. Neither is imported or
discovered, and their Python/YAML suffixes are outside the native scan. Their
finite admission preserves both complement identities; it does not approve the
producer workflow, enable reusable evidence or exempt neighboring files.

The two locks
`browser-client/package-lock.json` and
`script-archive/marketplace/S3Server/package-lock.json` form a separate conditional
class. They are not independent-host files and remain present in ordinary app
fingerprints. Their changed bytes can be omitted only for the immutable npm
selector's exact reviewed source-map-js/proxy-addr update, reviewed formatting,
or a complete required JavaScript package check for another lock graph change.
The latter keeps the full package build/function/security obligations and both
reviewed iOS reader boundaries. It never treats an unsupported dependency graph
as the focused security-fix profile or a passing package result.

The iOS route independently loads the trusted required package controller,
validates the complete five-workflow generation and recomputes the exact package
plan. Ownership requires explicit package activation or the deployed complete
mandatory five-workflow repository caller. The latter is already enforced by the
independently required `repository-checks` aggregate. The iOS selection binds the
package candidate, plan, trusted policy and dependency profiles. That aggregate
still requires successful same-candidate package receipts; an iOS omission is
not a package test receipt and cannot make a failing package check mergeable.

Both app and own-host reader complements remain bound independently on both
immutable trees. The app reader complement contains 10,964 entries and is
`sha256:cba03775542c32affcfe172b66b80b23cab31abd9f61293abd3f5cb0e19c03e8`;
the own-host complement is
`eb10f2ce89017a4efc75001773c1da415994dc2f4d542fb2804183bc2f77ba15`.
These protected-`apple-ios` reader identities normalize only the finite lock
class; they do not approve arbitrary lock graphs. Missing or unsupported owners,
changed package consumers/configuration, native sources, discovery membership,
unknown paths, modes, symlinks and historical reader drift retain the relevant
full iOS gate. All real CMake, QML, platform inputs and the Appium lock stay bound.

The protected launcher discovers only the iOS release-check and device self-test
roots. Its repository-wide Core5Compat scan reads native source suffixes, which
exclude these CI helpers, templates and locks. Release-check lock inventory is
restricted by its explicit source scope, outside both package roots. This source
extension does not establish hosted child qualification or produce an IPA. The
original bootstrap guard and legacy generation remain unchanged.

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
