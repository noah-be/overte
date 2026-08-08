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

## 06 — Complete device-free regression gate

- Branch: `nightly/android-phone-06-complete-static-gate`
- Commit: `Add complete phone static regression gate` (this task's commit)
- Change: Add one explicit allowlist runner for all 32 proven device-free Phone
  suites. It covers source/static contracts, C++ fixtures, Java compilation,
  JavaScript syntax and mocks, packaging fixtures, release/16-KiB checks, and
  the mock-ADB deployment/benchmark harnesses. The real device and real
  graphics-benchmark scripts are intentionally absent and cannot be discovered
  by wildcard.
- Tests:
  - Pre-integration run of every `phone-*-test.sh` and contract script except
    the two real device runners: **passed**.
  - `android/tests/serverless-hub-fixture-test.sh`: **passed** (136 entities,
    schema and referenced scripts valid).
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 32
    allowlisted suites; nested host regression passed 174/174 checks.
  - `git diff --check`: **passed**, both directly and as the final aggregate
    gate step.
- Known risks and deferred audit: The tablet still uses a symmetric 25 Qt
  logical-pixel safety inset. Real asymmetric Android cutout/rounded-corner
  insets are not transported from Java to the Qt tablet presenter. Guessing
  them from display size was rejected; a future Java→JNI→presenter contract
  needs device validation. Current resize, portrait-transition fallback, and
  minimum-size guards remain covered.
- Real-device validation still required: **not executed**. Besides the full
  device checklist below, exercise left/right landscape rotations on flat,
  notched, hole-punch, waterfall, and rounded-corner displays; verify all
  tablet edges and close controls remain reachable and no content lies under a
  cutout or transient system bar.

## 05 — Native touch Emote

- Branch: `nightly/android-phone-05-emote-audit`
- Commit: `Add native Android phone Emote app` (this task's commit)
- Change: Add a Phone-only native QML Emote grid and lifecycle-owned script.
  Requests are namespaced and allowlisted, unavailable resources fail safely,
  timers and avatar overrides are cleaned up deterministically, and the app has
  no Web surface, controller mapping, or mutable QML button-proxy dependency.
  More remains disabled because it downloads remote metadata and installs
  third-party scripts; Create remains disabled by its existing isolation gate.
- Tests:
  - `android/tests/phone-tablet-emote-test.sh`: **passed**, 14 source
    contracts, JavaScript syntax, and the lifecycle mock.
  - `android/tests/phone-tablet-emote-lifecycle-mock.js`: **passed** for open,
    ready, invalid request, play, same-action stop, timer cancellation, avatar
    restoration, signal disconnection, and button removal.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, JavaScript syntax checks, and 174/174 host checks.
  - Qt 6 `qmllint` on `PhoneEmote.qml`: **passed** with non-fatal Qt 6
    unqualified-access warnings for Qt 5-compatible delegate context access.
  - `android/tests/phone-script-payload-test.sh`: **passed** again after the
    new assets became tracked; all required defaults and payload exclusions
    remain consistent.
  - `git diff --check`: **passed**.
- Known risks: Animation availability and visual behavior depend on runtime
  resource loading. Playback deliberately uses a finite timer for every emote,
  including Sit, instead of installing the legacy controller mapping.
- Real-device validation still required: **not executed**. Open/close/reopen
  Emote, trigger every action after cold and warm cache, stop an action by
  tapping it again, switch actions rapidly, move during Sit, background and
  foreground during playback, and confirm the avatar always returns to its
  locomotion animation with no stale highlighted state.

## 04 — Background, Back, and IME lifecycle

- Branch: `nightly/android-phone-04-lifecycle-audit`
- Commit: `Harden Android phone lifecycle state` (this task's commit)
- Change: Mark Qt Hidden/Suspended states as non-foreground, clear transient
  consumed-Back bookkeeping on Activity pause, and add an Address dialog
  destruction fallback that drops field focus and hides the IME. Existing
  pending-deep-link callbacks remain pause-aware and are not discarded.
- Tests:
  - `android/tests/phone-app-lifecycle-test.sh`: **passed**, 5 lifecycle
    contract checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, JavaScript syntax checks, and 174/174 host checks.
  - `git diff --check`: **passed**.
- Known risks: The shared foreground flag now reflects Qt's documented Hidden
  and Suspended states on every platform. Inactive remains distinct so a
  temporarily unfocused but visible desktop window is not treated as hidden.
- Real-device validation still required: **not executed**. While Address and
  Login dialogs respectively have the IME raised, background/foreground the
  app, use physical and gesture Back, reopen each dialog, and verify no stale
  key-up, keyboard, focus, or touch capture remains. Repeat while a deep link
  arrives during cold startup and while the app is paused.

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
