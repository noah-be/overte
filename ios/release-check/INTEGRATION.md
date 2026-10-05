# Prerelease gate integration — 2026-10-05

This integrates the retained implementation from
`task/ios/948-prerelease-quality-gate` into the maintained `apple-ios` baseline.
All five original commits remain in the merge ancestry. Historical qualification
records retain their original revision and scope; they are not new release
acceptance records.

## Reviewed implementation

The local checker consumes explicitly supplied build, artifact and device
evidence. Its default command does not build, install, sign or publish. Missing
or changed evidence still fails; partial checks do not print a release PASS.
Private configuration and diagnostic reports remain outside the checkout.

The retained 38 Python regression tests and shipped users-event regression are
now part of the ordinary iOS host suite. They cover archive boundaries, stale
source/attribution data, copied device results, telemetry rejection and partial
acceptance. They are checker tests, not physical-device acceptance.

The two shared `tablet-users.js` corrections belong to `main`. Their retained
behavior regression also runs in the shared JavaScript suite. They are forwarded
through `apple-main` before this product integration; no product branch is
merged into a parent or sibling.

The dispatch-only inspector's `ios-release-check` runner label is registered
in the canonical Actionlint inventory on `main` and forwarded through
`apple-main`. Registration does not provision a runner or dispatch an
inspection. The existing workflow lint and security checks remain enabled.

## Historical failed builds

The first hosted attempt,
[35466963156](https://github.com/noah-be/overte/actions/runs/35466963156), failed
the host workflow classification before a macOS client build. The original
follow-up repaired those contracts; that history remains in `FOLLOWUP.md`.

The subsequent attempt,
[35467154128](https://github.com/noah-be/overte/actions/runs/35467154128), passed
host/gate contracts and Qt/V8 provisioning but failed the Full Client compilation:
`WindowScriptingInterface.cpp` included `AndroidHelper.h` on iOS. The maintained
`apple-ios` baseline already guards that include and the related Android headers
with `Q_OS_ANDROID`. No additional native-source repair is introduced here.
Later device-build qualification, including
[37271613776](https://github.com/noah-be/overte/actions/runs/37271613776), succeeded
on the maintained product line. That evidence does not qualify the original
failed revision or establish a cold production build for this integration.

The required `ios-device-build` check qualifies the exact integration candidate
with an unsigned E2E build. It uses the existing Qt/compiler checkpoints and
does not satisfy the checker's separate cold production-build receipt. No extra
manual production build, device campaign or long-running test is needed merely
to retain this implementation on its owner branch.

## Remaining release qualification

Integration does not approve an iOS release. Historical scanner findings still
need their recorded disposition, and the checker still requires real dependency
and SDK provenance, asset/privacy reviews, cold-build and artifact evidence, and
candidate-bound physical-device results before full release acceptance. No
unknown evidence is supplied or converted into a PASS.

Issue [#948](https://github.com/noah-be/overte/issues/948) remains open for the
owner's disposition. Automatic branch cleanup may retire the topic branch only
after its exact head is retained by the protected product target.
