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
- Commit: `6fc87f06e6` (`Harden Pico OpenXR loader lifecycle`)
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

### 05 — Unified device-free regression suite

- Branch: `nightly/pico4-05-device-free-suite`
- Commit: `cf8f38fbd3` (`Add Pico device-free regression suite`)
- Change: add one explicitly ADB-free entry point for shell syntax, WebView,
  AudioRecord, OpenXR loader, microphone/unattended/device-lock mocks,
  serverless fixture integrity, and power-analyzer coverage; document its
  separation from configured native Qt/C++ host tests.
- Passed: `android/tests/pico-device-free-test.sh` in full: WebView bridge (3),
  WebView gesture state, AudioRecord state, OpenXR lifecycle (3), microphone
  mocks (11), unattended mocks (9), device-lock mocks (5), serverless fixture,
  power analyzer (4), and all selected Bash syntax checks.
- Risk: this suite intentionally does not imply that native compilation,
  Android packaging, or headset behavior passed.
- Pico 4 validation: **not executed**. No additional device procedure is
  introduced by this test-runner-only task; execute the cumulative checks below.

### 06 — WebView navigation and background state

- Branch: `nightly/pico4-06-webview-navigation-state`
- Commit: `2147fb218b` (`Reset Pico WebView navigation state`)
- Change: apply `useBackground` to Android WebView as opaque white or
  transparent, and cancel active touch plus fractional scroll state before
  navigating an existing offscreen WebView to a new document.
- Regression: WebView bridge source contracts now cover background forwarding
  and navigation cleanup in addition to frame/JNI/input behavior.
- Passed: full `pico-device-free-test.sh`; WebView bridge (5), gesture state,
  AudioRecord state, OpenXR lifecycle (3), microphone mocks (11), unattended
  mocks (9), device-lock mocks (5), fixture integrity, power analyzer (4), and
  shell syntax; `git diff --check`.
- Risk: host checks cannot visually prove alpha compositing or Android's page
  transition behavior.
- Pico 4 validation: **not executed**. Compare otherwise identical Web entities
  with `useBackground` true/false over contrasting geometry; navigate while
  pressed and after a sub-wheel scroll, then verify no click, drag, hover, or
  fractional scroll leaks into the destination page.

### 07 — Fast interaction transition diagnostics

- Branch: `nightly/pico4-07-interaction-transition-diagnostics`
- Commit: `887cfd93e7` (`Capture fast Pico input transitions`)
- Change: sample the opt-in Pico controller diagnostic on `Script.update`
  instead of every 100 ms, separately count trigger-click and tracking-validity
  transitions, and keep verbose snapshots throttled to one second.
- Regression: a Node mock drives a rapid trigger/click press-release and a
  tracking loss/recovery, then asserts exact summary counters and logs.
- Passed: JavaScript syntax for diagnostic and test; interaction diagnostic
  mock; full `pico-device-free-test.sh` including all task-06 results plus the
  new interaction test; `git diff --check`.
- Risk: the diagnostic is opt-in but samples two controller states each frame;
  only transitions and one-second summaries log. Host mocks cannot reproduce
  OpenXR event coalescing below one rendered frame.
- Pico 4 validation: **not executed**. Run rapid trigger and grip taps, click
  near the runtime threshold, alternate hands/targets, cover and uncover each
  controller, and verify transition counts and recovery logs against a video or
  independent input trace; confirm the diagnostic itself does not alter grabs.

### 08 — Fail-closed OpenXR axis state

- Branch: `nightly/pico4-08-openxr-stale-axis-state`
- Commit: `2ce1e7f72d` (`Clear stale Pico OpenXR axis state`)
- Change: clear Pico OpenXR axis state at the start of every input update,
  alongside pose and button state. Inactive actions after tracking/profile loss
  now resolve to neutral rather than retaining trigger, grip, or stick values.
- Regression: source-level OpenXR input contract verifies all transient maps
  clear before no-session returns and action sync, while only active float
  actions repopulate axes.
- Passed: OpenXR input regression (2); full `pico-device-free-test.sh` including
  all prior suites; `git diff --check`.
- Risk: neutral-on-inactive follows OpenXR's action-state contract and existing
  button behavior, but physical runtime transition timing remains unobserved.
- Pico 4 validation: **not executed**. Hold trigger, grip, and each stick away
  from neutral while hiding or powering down one controller; verify all axes
  immediately return to neutral, active grabs/clicks release safely, locomotion
  stops, and values recover normally when tracking returns.

### 09 — Fail-closed OpenXR action sync

- Branch: `nightly/pico4-09-openxr-sync-fail-closed`
- Commit: `b1c7121e28` (`Fail closed on Pico OpenXR sync errors`)
- Change: return immediately after a failed `xrSyncActions`, leaving the maps
  cleared by task 08 rather than querying potentially stale runtime action data.
- Regression: OpenXR input contract now asserts the guarded early return.
- Passed: OpenXR input regression (3); full `pico-device-free-test.sh` including
  all prior suites; `git diff --check`.
- Risk: this deliberately drops one failed input frame; continued runtime
  failure remains visible through the existing critical OpenXR error log.
- Pico 4 validation: **not executed**. Exercise suspend/resume and controller
  reconnect paths that can interrupt action sync; verify no stale grab, click,
  locomotion, or scroll occurs and input resumes after the runtime recovers.

### 10 — Final scope and documentation audit

- Branch: `nightly/pico4-10-final-audit`
- Commit: identified by subject `Document remaining Pico validation`; the exact
  hash is reported in the final session summary.
- Change: reconcile the contradictory off-hand-rotation documentation with the
  inherited desktop implementation; record build blockers, deliberately
  deferred work, remaining device-free limits, and the final headset order.
- Passed: final device-free suite, syntax checks, repository scope review,
  branch-chain review, clean-worktree and diff checks recorded after commit.
- Pico 4 validation: **not executed**. This documentation-only task introduces
  no new runtime behavior.

## Deferred, rejected, or blocked ideas

- Full `scriptURL`, Qt WebChannel, and bidirectional `EventBridge` emulation for
  Android WebView was not implemented. It defines a page-to-native security
  boundary and compatibility API that needs a reviewed protocol, origin/frame
  policy, Android integration build, and real page acceptance tests. A partial
  JavaScript interface would be less safe than the documented limitation.
- Tablet/HUD Web surfaces remain separate from the Pico world-Web-entity
  bridge, as established by the renderer audit. Replacing them would expand
  scope and risk already working UI paths.
- Grab-latency, ray offsets, visual alpha quality, audio quality/AEC, thermal
  behavior, and render parameters were not tuned. Their effect cannot be
  established without physical controllers, display/audio observation, or a
  headset; diagnostics and exact checks are provided instead.
- Off-hand rotation was not reimplemented because Pico already inherits the
  desktop mapping. Only the inaccurate validation status was corrected.
- Create/Entity List/import/native QML, avatar/mirror/secondary-camera, and
  world/reconnect paths showed no additional narrow defect that could be
  responsibly changed within the available device-free evidence. Existing
  Pico code in these broad areas requires configured native builds and targeted
  runtime scenarios before behavioral changes.
- Native Qt/C++ host suites are blocked in this worktree: `build-tests` has no
  `CMakeCache.txt`. The Pico Android build is also blocked before compilation by
  missing `android/conan/pico4-debug/generators/Qt5-debug-armv8-data.cmake`.
  Dependencies were not downloaded or installed during this session.

## Remaining work

1. Restore/bootstrap the documented Pico Conan/Qt dependencies, compile the
   Android Java/JNI/C++ changes, package the APK, and run the configured native
   host regression suites.
2. Design and review the WebChannel/EventBridge security and compatibility
   contract before implementing `scriptURL` or page-to-entity messaging.
3. Execute the cumulative physical-headset checks below and use their traces to
   decide whether grab/pointer performance work or pose correction is justified.
4. Investigate the broad Create, avatar/camera, and reconnect areas only from a
   reproducible failing scenario or a new device-free unit seam.

## Cumulative remaining device validation

1. OpenXR fail-closed behavior: hold trigger/grip/sticks, interrupt tracking,
   suspend/resume, and reconnect; confirm immediate neutral state, safe release,
   and recovery with no stale click, grab, locomotion, or scroll.
2. Fast interaction transitions: compare the new per-frame diagnostic counts
   with physical actions; cover target changes, alternating hands, tracking
   loss/recovery, and inherited off-hand rotation.
3. Web entities: opaque/transparent backgrounds, transparent-centre content,
   repeated resize/navigation/destruction, both-hand hover/click/drag/scroll,
   pressed target loss, multi-WebView isolation, and JNI/WebView error logs.
4. Microphone: rapid source switching and restart isolation, FIFO transport and
   backpressure, fixed-phrase speech quality, AEC/echo, and sustained capture
   with automatic fan control. Audio quality remains unconfirmed.
5. Loading/reconnect and UI regression: serverless and online world switches,
   tablet/HUD/Create/Entity List/import, local avatar, mirror/secondary camera,
   and Android Activity lifecycle.
6. Only after the correctness checks, profile grab/pointer/physics latency and
   measure ray alignment. Do not change thresholds, pose offsets, or performance
   parameters without those results.
