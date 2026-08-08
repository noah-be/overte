# Nightly Pico 4 work

This log covers autonomous, device-free work based on
`origin/feature/pico4-support`. Branches are stacked in the order listed. No
headset, ADB, Android device, external domain, or device setting is used.

## 2026-08-08

### 01 — WebView frame lifecycle

- Branch: `nightly/pico4-01-webview-frame-lifecycle`
- Commit: `3352e35674` (`Harden Pico WebView frame delivery`)
- Change: accept valid transparent WebView frames instead of treating a
  transparent centre pixel as an unready surface; reject invalid dimensions,
  multiplication overflow, null direct-buffer addresses, and undersized JNI
  frame buffers before constructing a `QImage`.
- Regression: `python3 android/tests/pico-webview-bridge-test.py`.
- Passed: WebView bridge regression (2 tests); microphone runner mocks (11);
  unattended runner mocks (9); serverless fixture integrity; Pico device-lock
  mocks (5); Bash syntax for `android/tests/*.sh` and `android/*.sh`.
- Risk: the source-level bridge test cannot exercise Android WebView rendering
  or the Qt scene graph. The checks are deliberately narrow and complement an
  Android build and later acceptance test.
- Pico 4 validation: **not executed**. Load both an opaque page and a page with
  a transparent centre/background, verify content away from the centre renders,
  resize each entity repeatedly, then delete it during active rendering and
  check logcat for JNI/WebView errors or stale frames.

### 02 — WebView input gesture state

- Branch: `nightly/pico4-02-webview-input-state`
- Commit: `268d37ab22` (`Preserve Pico WebView input gestures`)
- Change: preserve Android's original `downTime` across down/move/up/cancel,
  send the correct hover-enter action, cancel an active touch when Qt revokes
  the mouse grab, and cancel before an offscreen WebView is destroyed.
- Regressions: pure-Java touch-state test plus source-level Qt/JNI bridge test.
- Passed: `pico-webview-input-test.sh`; WebView bridge regression (3 tests);
  Bash syntax for the new runner; `git diff --check`.
- Build not run: offline Gradle configuration stops before Java compilation
  because `android/conan/pico4-debug/generators/Qt5-debug-armv8-data.cmake` is
  absent. No dependency installation or network fetch was attempted.
- Risk: Android dispatch and physical ray behavior remain outside a host JVM.
  The extracted state machine itself has no Android dependency and covers
  normal completion, cancellation, consecutive gestures, and orphan moves.
- Pico 4 validation: **not executed**. Rapidly press, drag off target, release,
  alternate targets and hands, delete a pressed Web entity, and confirm there
  is exactly one click/release with no stuck pressed or hover state.

### 03 — Microphone stale-capture isolation

- Branch: `nightly/pico4-03-microphone-stale-capture`
- Commit: `423221f3ed` (`Discard stale Pico microphone reads`)
- Change: after each blocking `AudioRecord.read()`, deliver bytes only if
  capture is still running and the reader is still the current recorder. This
  prevents a final old-source buffer from entering the FIFO after stop, source
  switch, or restart.
- Regression: pure-Java lifecycle guard covering active, stopped, replaced,
  empty, and failed reads.
- Passed: `pico-audio-capture-state-test.sh`; microphone runner mocks (11);
  Bash syntax for the new runner; `git diff --check`.
- Risk: the JVM test proves the delivery decision, not AudioRecord's device-
  specific unblock timing or captured audio quality.
- Pico 4 validation: **not executed**. Switch repeatedly among microphone
  sources while speaking distinct markers, stop/restart capture during input,
  and verify the first buffer after each switch belongs only to the new source;
  then run the documented transport/backpressure and long-duration checks.

### 04 — OpenXR loader JNI lifecycle

- Branch: `nightly/pico4-04-openxr-loader-lifecycle`
- Commit: identified by subject `Harden Pico OpenXR loader lifecycle`; the
  exact hash is recorded by the following stacked task or the final report.
- Change: construct Activity/application-context global references as a
  temporary set, publish them only after loader initialization succeeds, clean
  every early failure path, release the Activity-class local reference, and on
  Activity recreation reuse the process-global loader while replacing only the
  Activity reference.
- Regression: `python3 android/tests/pico-openxr-loader-test.py` checks the
  recreation, transactional-publication, and local-reference contracts.
- Passed: OpenXR loader lifecycle regression (3 tests); `git diff --check`.
- Build not run: the Pico Conan/Qt generator metadata needed by the Android
  build is absent in this worktree, as documented in task 02.
- Risk: the source-level test cannot create a real Pico OpenXR loader or force
  Android Activity recreation during an active XR session.
- Pico 4 validation: **not executed**. Cold-start repeatedly, background and
  resume the app, trigger Activity recreation if supported, then confirm a
  single loader initialization, a refreshed Activity, no invalid JNI reference,
  and successful session creation after each lifecycle transition.

## Cumulative remaining device validation

1. Web entity transparent-content, resize, destruction, and navigation checks
   described above.
2. Both-controller hover, click, drag, scroll, target-loss, and stuck-input
   checks from `pico4-web-entities.md`.
3. Microphone speech quality, AEC/echo, restart, source switching, and sustained
   automatic-fan tests from `pico-microphone.md`.
4. Grab latency and fast trigger/grip transitions with physical OpenXR input.
