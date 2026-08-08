# Android phone nightly work

This file records the cumulative, device-free Android phone work based on
`origin/feature/android-phone-support`. Real-device and emulator tests are out
of scope for this worktree and are called out explicitly where still needed.

## 01 — Host regression from any working directory

- Branch: `nightly/android-phone-01-host-test-cwd`
- Commit: `Fix phone host regression working directory` (this task's commit)
- Change: Resolve the Gradle input of the inline `awk` contract check from the
  script's already-normalized Android root. The advertised root-level command
  now exercises all checks instead of producing a false failure.
- Tests:
  - Before the fix, `./android/tests/phone-host-regression-test.sh`: **failed**,
    173 of 174 checks passed; `awk` could not open
    `apps/phoneInterface/build.gradle` from the repository root.
  - Before the fix, `(cd android && ./tests/phone-host-regression-test.sh)`:
    **passed**, 174 of 174 checks.
  - After the fix, `./android/tests/phone-host-regression-test.sh` from the
    repository root: **passed**, 174 of 174 checks.
  - After the fix, the same absolute script command from `/tmp`: **passed**,
    174 of 174 checks.
  - `git diff --check`: **passed**.
- Known risks: None in runtime code; this changes only a source-based host test.
- Real-device validation still required: **not required for this test-only
  change; not executed**.

## 02 — Fail-closed Phone General Settings

- Branch: `nightly/android-phone-02-settings-contract`
- Commit: `Remove VR-only phone preferences` (this task's commit)
- Change: Replace the inherited broad General Settings list with an explicit
  phone allowlist: Phone Navigation, touch-look sensitivity, and Privacy. This
  removes categories whose complete shared contract still contains desktop
  toolbar/tablet, desktop filesystem, HMD, VR laser/keyboard, or Oculus-only
  behavior. Desktop and VR category selection is unchanged.
- Tests:
  - `android/tests/phone-tablet-general-preferences-test.sh`: **passed**,
    7 contract checks.
  - `(cd android && ./tests/phone-tablet-static-test.sh)`: **passed**,
    including all tablet suites, JavaScript syntax checks, and 174/174 host
    regression checks.
  - `./android/tests/phone-tablet-static-test.sh` from the repository root:
    **failed** in the pre-existing modern-API test because three inputs are
    resolved relative to the caller. The same gate passes from its documented
    Android working directory; the CWD defect is queued as the next task.
  - QML lint: **not executed**; `qmllint` is not installed on this host. The
    selector syntax is covered by source-contract checks.
  - `git diff --check`: **passed**.
- Known risks: Touch-look sensitivity is retained because its yaw/pitch values
  are consumed by the shared avatar drive path. Privacy actions still require
  runtime confirmation of their Android integrations.
- Real-device validation still required: **not executed**. Confirm all three
  retained sections render, scroll, save/cancel correctly, and that pinch and
  X/Y sensitivity changes affect touch navigation after restart. Confirm each
  Privacy toggle has the expected Android behavior.

## 03 — Working-directory-independent static gate

- Branch: `nightly/android-phone-03-static-gate-cwd`
- Commit: `Fix modern Android test working directory` (this task's commit)
- Change: Resolve all remaining Modern Android API test inputs from its
  normalized repository root. This makes the test itself and the aggregate
  tablet static gate independent of the caller's working directory.
- Tests:
  - `android/tests/phone-modern-android-api-test.sh`: **passed**, 15 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, JavaScript syntax checks, and 174/174 host checks.
  - Absolute aggregate-gate invocation from `/tmp`: **passed** with the same
    complete result.
  - `git diff --check`: **passed**.
- Known risks: None in runtime code; this changes only source-test paths.
- Real-device validation still required: **not required for this test-only
  change; not executed**.
