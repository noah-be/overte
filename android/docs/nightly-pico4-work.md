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
- Commit: `09154d977c` (`Document remaining Pico validation`)
- Change: reconcile the contradictory off-hand-rotation documentation with the
  inherited desktop implementation; record build blockers, deliberately
  deferred work, remaining device-free limits, and the final headset order.
- Passed: final device-free suite, syntax checks, repository scope review,
  branch-chain review, clean-worktree and diff checks recorded after commit.
- Pico 4 validation: **not executed**. This documentation-only task introduces
  no new runtime behavior.

### 11 — Dispatcher slot release

- Branch: `nightly/pico4-11-dispatcher-slot-release`
- Commit: `85209bedc1` (`Release deactivated controller slots`)
- Change: when a running controller module disappears, test property ownership
  on the dispatcher slot table rather than on the slot-name string. Matching
  hand/trigger activity slots are now actually returned to the dispatcher.
- Regression: the Node interaction test asserts the correct ownership target
  and rejects the ineffective string ownership expression.
- Passed: dispatcher and test JavaScript syntax; interaction Node test; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: this fixes a shared dispatcher defect because Pico dynamically switches
  several grab, Web, HUD, keyboard, and Create modules over the same hand slots.
- Pico 4 validation: **not executed**. Disable or unload a module while it owns
  each hand/trigger slot, then immediately start another module on that slot;
  verify interaction resumes without restarting controller scripts.

### 12 — Off-hand tracking-loss rotation guard

- Branch: `nightly/pico4-12-offhand-tracking-loss`
- Commit: `48ba7b20b3` (`Guard Pico off-hand rotation tracking`)
- Change: far-grab rotation consumes the other controller's quaternion only
  while its current pose is valid. Tracking loss ends manipulation through the
  existing preservation path, retaining the last valid entity rotation.
- Regression: the Node interaction contract requires the current valid-pose
  guard and rejects the former unguarded `pose.rotation` expression.
- Passed: far-grab and test JavaScript syntax; interaction Node test; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: this changes shared far-grab code to fail closed, matching the Pico
  tracking-loss requirement without changing manipulation thresholds or math.
- Pico 4 validation: **not executed**. Rotate a far-grabbed object with the
  other hand, interrupt only that hand's tracking, and verify the object keeps
  its last valid rotation, translation continues with the grabbing hand, and
  rotation resumes smoothly after a fresh manipulation press.

### 13 — Tracked-controller availability

- Branch: `nightly/pico4-13-openxr-tracked-controller-count`
- Commit: `fefc212f07` (`Count valid Pico controller poses`)
- Change: reset the OpenXR tracked-controller count to zero each input update
  and increment it only for controller locations with a valid orientation.
  Missing sessions, sync failures, and total tracking loss no longer report two
  permanently available controllers.
- Regression: OpenXR input tests assert the pre-return zero reset, valid-pose
  increment, and absence of the former constant-two assignment.
- Passed: OpenXR input regression (4); full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: availability now reflects current pose validity, as downstream
  dispatcher diagnostics expect; runtime-specific transient validity still
  needs headset observation.
- Pico 4 validation: **not executed**. Test zero, one, and two visible
  controllers, full tracking loss, session suspend/resume, and recovery; compare
  `HMD.isHandControllerAvailable()` and diagnostic poses with physical state.

### 14 — Android restart argument isolation

- Branch: `nightly/pico4-14-android-restart-arguments`
- Commit: `7ca079b3d2` (`Protect Pico restart arguments`)
- Change: make the internal Qt Activity non-exported; move process-restart
  arguments from an externally injectable Intent string to one-shot private app
  preferences; stop logging the argument contents; abort restart if durable
  private storage fails.
- Regression: XML/Java contracts verify launcher/export boundaries, absence of
  external string ingestion, private storage, one-shot removal, and redacted
  restart logging.
- Passed: Android entry-point regression (3); full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: the exported launcher remains required by Android/Pico OS, but it can
  now request only consumption of app-generated state rather than supply raw
  arguments. The private write uses synchronous commit because the process is
  deliberately killed shortly afterward.
- Pico 4 validation: **not executed**. Launch normally, change Pico render scale
  to exercise process restart, verify arguments survive exactly once, then send
  explicit external intents and confirm raw arguments cannot reach Qt.

### 15 — Permission Activity recreation

- Branch: `nightly/pico4-15-permission-activity-recreation`
- Commit: `e83e049e32` (`Preserve Pico restart permission state`)
- Change: preserve consumed restart arguments across Android Activity
  recreation and make Interface launch idempotent across lifecycle and
  permission callbacks.
- Regression: Android entry-point tests require saved/restored arguments,
  persisted launch state, and duplicate-launch guards.
- Passed: Android entry-point regression (4); full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: state remains process-local plus Android-managed instance state; a full
  process death correctly falls back to the private persisted handoff until it
  is consumed by the first launcher instance.
- Pico 4 validation: **not executed**. Recreate the launcher during the first
  microphone permission prompt and during a render-scale restart; verify one
  Interface Activity starts with the intended arguments in both grant and deny
  cases.

### 16 — Activity shutdown cleanup

- Branch: `nightly/pico4-16-activity-shutdown-cleanup`
- Commit: `8c031d0ca1` (`Clean up Pico Activity resources`)
- Change: on Qt Activity destruction, synchronously destroy every offscreen
  WebView when already on Android's main thread, stop AudioRecord, and clear the
  static Activity reference. Off-thread bulk WebView cleanup is safely posted.
- Regression: Android lifecycle contracts require all three cleanup actions and
  snapshot iteration over the WebView registry.
- Passed: Android entry-point/lifecycle regression (5); full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: native Web entity destructors may subsequently request individual
  destruction, which is intentionally idempotent against the emptied registry.
- Pico 4 validation: **not executed**. Recreate, finish, and restart the
  Activity with active Web entities and microphone capture; verify old frame
  callbacks/audio reads stop and the new Activity starts with fresh resources.

### 17 — Native OpenXR Activity release

- Branch: `nightly/pico4-17-openxr-activity-release`
- Commit: `f63fe424d7` (`Release Pico OpenXR Activity reference`)
- Change: release the native OpenXR loader's global Activity JNI reference from
  `onDestroy()`, but only when `IsSameObject` proves the destroying Activity is
  still the published instance. The process-global application Context remains
  available for loader reuse.
- Regression: loader tests verify identity guarding, global-ref deletion, and
  nulling; Android lifecycle tests require the release hook.
- Passed: OpenXR loader regression (4), Android lifecycle regression (5), full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: JNI publication remains confined to Android lifecycle calls; the
  identity guard protects a newer Activity from a late old-instance destroy.
- Pico 4 validation: **not executed**. Recreate Activities rapidly and inspect
  logcat/native behavior for stale or prematurely cleared Activity references
  while OpenXR sessions stop and restart.

### 18 — OpenXR action query failures

- Branch: `nightly/pico4-18-openxr-action-errors`
- Commit: `4f591968d9` (`Fail closed on Pico OpenXR action errors`)
- Change: Float, vector, boolean, pose-state, and pose-location queries return
  deterministic inactive/neutral values when OpenXR reports an error. Pose
  spaces are located only for active actions, and a failed locate returns an
  invalid location rather than partially populated data.
- Regression: OpenXR input contracts cover neutral action return types,
  active-pose gating, locate failure, and false activity on query failure.
- Passed: OpenXR input regression (6); full `pico-device-free-test.sh`;
  Python syntax; `git diff --check`.
- Risk: dropping invalid action data matches OpenXR's failure semantics and the
  input maps' fail-closed policy; runtime error frequency remains device-only.
- Pico 4 validation: **not executed**. Exercise controller sleep/reconnect and
  Activity/session transitions; verify failed queries cannot revive old poses,
  buttons, axes, grabs, rays, or locomotion.

### 19 — OpenXR haptic device bounds

- Branch: `nightly/pico4-19-openxr-haptic-index`
- Commit: `4532675ea0` (`Reject invalid Pico haptic indices`)
- Change: reject haptic device indices greater than or equal to the two-hand
  OpenXR count. Index 2 can no longer be silently redirected to the right hand.
- Regression: OpenXR input test requires the `HAND_COUNT` bound and rejects the
  former `index > 2` condition.
- Passed: OpenXR input regression (7); full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: valid left/right indices remain unchanged; non-hand devices now fail
  explicitly instead of producing misleading right-controller feedback.
- Pico 4 validation: **not executed**. Trigger left/right haptics separately and
  submit an invalid test index; verify only indices 0 and 1 vibrate.

### 20 — Strict WebView touch sequences

- Branch: `nightly/pico4-20-webview-touch-sequences`
- Commit: `4e82d00a32` (`Validate Pico WebView touch sequences`)
- Change: cancel an existing WebView gesture before accepting a replacement
  Down, and discard Move/Up/Cancel events that have no active Down. Valid
  gestures continue to preserve their original Android `downTime`.
- Regression: WebView bridge contracts cover both sequence guards; the pure-
  Java state test covers cancel-plus-replacement timestamp behavior.
- Passed: WebView bridge regression (6), gesture-state JVM regression, full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: malformed streams now fail closed instead of being interpreted by
  Android WebView; normal hover and single-touch sequences are unchanged.
- Pico 4 validation: **not executed**. Generate rapid repeated trigger presses,
  target switches, release outside the page, and page deletion; verify every
  new press begins cleanly and no orphan event creates a click or stuck drag.

### 21 — WebView creation failures

- Branch: `nightly/pico4-21-webview-creation-failures`
- Commit: `342f44ee45` (`Handle Pico WebView creation failures`)
- Change: reject offscreen WebView creation when the Pico Activity is absent,
  and catch Android WebView-provider/runtime construction failures on the main
  thread. Density is read from the validated local Activity instance. The
  whole-document flag is committed only after successful construction.
- Regression: WebView bridge contracts require Activity guarding, caught
  provider failures, local Activity construction, and absence of the former
  unchecked dereference.
- Passed: WebView bridge regression (7); full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: the affected Web entity remains blank rather than crashing the whole
  process; recovery after Activity recreation occurs through newly constructed
  QML/native surfaces.
- Pico 4 validation: **not executed**. Create/destroy Web entities during
  Activity shutdown/recreation and test a missing/disabled WebView provider on
  a disposable environment; confirm a diagnostic error without process death.

### 22 — Audio buffer configuration validation

- Branch: `nightly/pico4-22-audio-buffer-validation`
- Commit: `f53c813e10` (`Validate Pico audio buffer sizes`)
- Change: calculate PCM16 callback and AudioRecord buffer sizes with `long`
  intermediates; reject nonpositive rates/frame counts, channel counts other
  than mono/stereo, and values that exceed Java `int` before calling AudioRecord.
- Regression: pure-Java tests cover existing mono/stereo sizing, native and
  Android minimum selection, invalid fields, callback overflow, and doubled-
  recorder overflow.
- Passed: audio lifecycle/buffer JVM regressions; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: valid production format sizes are unchanged; malformed JNI inputs now
  fail startup with a diagnostic rather than wrap into an invalid allocation.
- Pico 4 validation: **not executed**. Confirm the normal 48 kHz mono source
  reports the unchanged 1920-byte callback and sustained capture behavior.

### 23 — Tablet lifecycle and local messages

- Branch: `nightly/pico4-23-tablet-lifecycle-messages`
- Commit: `a71e38a590` (`Harden Pico tablet script lifecycle`)
- Change: accept tablet control channels only from self-authored local messages;
  guard and validate hand parsing; on script end clear the update interval,
  disconnect both message handlers, unsubscribe all four owned channels, and
  disable both controller mappings.
- Regression: Node source contracts cover sender/locality checks, guarded hand
  parsing, allowed hands, interval cleanup, handler disconnect, channel
  unsubscribe, and mapping shutdown.
- Passed: tablet lifecycle regression; tablet script and test syntax; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: all known producers use `sendLocalMessage`; rejecting network copies
  closes an unintended control surface without changing normal tablet input.
- Pico 4 validation: **not executed**. Reload default scripts repeatedly while
  opening/closing/moving the tablet; verify one handler/mapping per action, then
  inject malformed and nonlocal channel messages and confirm they are ignored.

### 24 — Finite native Create properties

- Branch: `nightly/pico4-24-create-finite-properties`
- Commit: `b3f43daf2e` (`Validate Pico Create numeric values`)
- Change: normalize displayed and submitted Pico property numbers to finite
  values, require a positive finite focus step, and accept controller numeric
  adjustments only as the discrete directions -1 or 1.
- Regression: QML source contracts cover the shared finite-number helper,
  field/display conversion, direction validation, and step lower bound.
- Passed: native Create regression (3); Python syntax; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: malformed/nonfinite text now resolves to zero (dimensions retain their
  existing 0.001 minimum); ordinary finite editing behavior is unchanged.
- Pico 4 validation: **not executed**. Enter/paste invalid, infinite, signed,
  decimal, and extreme finite values into every native property field; confirm
  no invalid transform reaches the entity and normal stick adjustment remains.

### 25 — Create message property allowlist

- Branch: `nightly/pico4-25-create-message-validation`
- Commit: `92ca2ba9bd` (`Validate Pico Create property messages`)
- Change: validate QML Preview/Apply payloads again in `edit.js` through a
  shared allowlist module; require finite vectors/colors and strict booleans,
  clamp dimensions/colors, copy only supported properties, and reject missing
  IDs before string conversion. Unexpected entity fields cannot pass through.
- Regression: Node behavior tests cover valid copies, extra-field removal,
  infinity/NaN rejection, dimension minima, color bounds, and boolean types.
- Passed: Create validation Node test; module/edit/test JavaScript syntax; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: this deliberately narrows only the native Pico properties payload to
  fields its UI exposes; the desktop Web properties editor remains unchanged.
- Pico 4 validation: **not executed**. Preview/apply every exposed property and
  undo it; inject malformed QML messages and confirm no entity edit or script
  failure occurs.

### 26 — Tablet setting sanitization

- Branch: `nightly/pico4-26-tablet-setting-sanitization`
- Commit: `e834c23162` (`Sanitize Pico tablet settings`)
- Change: centralize Pico tablet distance, height, and tilt normalization;
  replace nonfinite persisted values with defaults and clamp finite values to
  the UI-supported ranges before spawn math or QML display.
- Regression: Node behavior tests cover defaults, numeric strings, NaN/
  infinities, and both range boundaries.
- Passed: tablet setting behavior test; affected JavaScript syntax; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: only the Pico-centered setting keys use the new helper; desktop/HMD
  legacy placement remains unchanged.
- Pico 4 validation: **not executed**. Seed corrupt and out-of-range settings,
  launch/open the tablet and position page, and verify finite bounded placement
  plus recovery through Apply/Reset.

### 27 — Avatar hot-path logging cleanup

- Branch: `nightly/pico4-27-avatar-hotpath-logging`
- Commit: `30d5be58b3` (`Remove always-on Pico avatar profiling`)
- Change: remove three always-on Android avatar timing collectors and their
  periodic info logs from per-frame local-avatar update/simulation paths. The
  Pico local-body optimization, avatar update, render transaction, and network
  send behavior remain unchanged.
- Regression: source contracts reject the removed profiler markers and verify
  that the Android-only local-body guard plus core update/send calls remain.
- Passed: avatar hot-path source contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: the coarse legacy periodic timing lines are no longer emitted. Existing
  `PerformanceTimer` scopes and opt-in detailed avatar diagnostics remain
  available without permanent release-build timestamp/log overhead.
- Pico 4 validation: **not executed**. Run normal navigation with log capture;
  confirm the three periodic profiler lines are absent and remote users still
  receive head/hand/avatar motion normally.

### 28 — Physics hot-path logging cleanup

- Branch: `nightly/pico4-28-physics-hotpath-logging`
- Commit: `4433258bb1` (`Remove always-on Pico physics profiling`)
- Change: remove the release-build per-step counters, timestamp, and periodic
  physics info log. Pico's existing late-frame substep cap and Bullet stepping,
  contact processing, outgoing-change signaling, and debug drawing are intact.
- Regression: source contracts reject the profiler state while requiring both
  hitch thresholds and the substep callback path to remain.
- Passed: hot-path source contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: the coarse once-per-second substep line is removed; Bullet profiling
  and existing physics diagnostic facilities remain available for deliberate
  captures.
- Pico 4 validation: **not executed**. Exercise collision-heavy grabbing and
  locomotion while capturing logs; verify normal physics behavior and absence
  of the periodic `PICO_PHYSICS_STEP` line.

### 29 — Entity hot-path logging cleanup

- Branch: `nightly/pico4-29-entity-hotpath-logging`
- Commit: `7e0f4185c8` (`Remove always-on Pico entity profiling`)
- Change: remove per-stage timestamps and periodic info logs from entity
  simulation and rendering, including two extra per-renderable timestamps and
  a once-per-second traversal of all pending renderables. Entity expiry,
  kinematics, sorting, scene transactions, workload updates, and enter/leave
  handling are unchanged.
- Regression: source contracts reject all three removed profiler families and
  require the functional simulation and renderer calls to remain.
- Passed: hot-path source contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: coarse always-on entity timing lines are removed. Existing scoped
  `PerformanceTimer`/`PROFILE_RANGE` instrumentation remains for intentional
  profiling without permanent runtime traversal and logging cost.
- Pico 4 validation: **not executed**. Load a dense online and serverless world,
  exercise animated/web/particle entities and enter/leave events, and confirm
  behavior remains correct with the periodic entity profiler lines absent.

### 30 — Pointer/pick hot-path logging cleanup

- Branch: `nightly/pico4-30-pointer-hotpath-logging`
- Commit: `1edc106997` (`Remove always-on Pico pointer profiling`)
- Change: remove per-pointer maps/counters, per-pick result timestamp insertion,
  five per-frame pick timestamps, periodic pick-cache scans, and their info
  logs. The pick time budget, active-hand full-rate policy, pointer event
  generation, and transition-only press/release diagnostic remain.
- Regression: source contracts reject the continuous profiler state while
  requiring the pick budget, active-ray path, result storage, event generation,
  and `PICO_POINTER_TRIGGER` transition diagnostic.
- Passed: hot-path source contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: continuous pick-age/stage logs are removed; discrete state transitions
  and existing scoped profiling still support stuck-click/grab investigations.
- Pico 4 validation: **not executed**. Exercise tablet/world rays, rapid target
  changes, tracking loss, click/drag/scroll, and both hands; confirm interaction
  plus transition traces without periodic latency log traffic.

### 31 — Application update hot-path logging cleanup

- Branch: `nightly/pico4-31-application-hotpath-logging`
- Commit: `0e1f07b865` (`Remove always-on Pico application profiling`)
- Change: remove 23 stage variables, their per-frame timestamp writes, the
  accumulator, and the unconditional once-per-second main-update timing log.
  The shared Pico update clock remains because it drives test controls,
  loading/reconnect state, and diagnostic property polling rather than profiling.
- Regression: source contracts reject the stage profiler and require the Pico
  state clock plus pick, pointer, entity, avatar, and render-update calls.
- Passed: hot-path source contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: the coarse aggregate update-stage line is removed. Existing scoped
  performance instrumentation remains available for deliberate profiling;
  no update ordering or Pico state-machine timing was changed.
- Pico 4 validation: **not executed**. Navigate online/serverless worlds while
  interacting and capturing logs; confirm normal loading, input, physics,
  avatars, and rendering without periodic `PICO_UPDATE_STAGES` output.

### 32 — Fail-closed serverless parsing

- Branch: `nightly/pico4-32-serverless-parse-failure`
- Commit: `314278d8b1` (`Reject invalid Pico serverless scenes`)
- Change: make serverless scene preparation report parse success separately
  from its potentially empty named-path map. Local and requested malformed
  scenes now return before changing session UUID/permissions, announcing a
  serverless connection, incrementing full-scene state, or committing the Pico
  import.
- Regression: source contracts verify parse failure precedes every external
  state mutation and that both synchronous-local and asynchronous-request paths
  return before connection/commit while valid empty named-path maps remain valid.
- Passed: world-loading failure-path contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: malformed files which were previously misreported as loaded now remain
  in the current loading/error state. Valid scenes, including those with no
  named paths, retain their existing import sequence.
- Pico 4 validation: **not executed**. Navigate from a playable online and local
  scene to malformed, empty-valid, and normal serverless files; verify malformed
  input never reports READY or replaces session/permissions, then recover by
  navigating to a valid scene.

### 33 — Serverless request generation ownership

- Branch: `nightly/pico4-33-serverless-request-generation`
- Commit: `2954fc6c49` (`Ignore stale Pico serverless requests`)
- Change: assign a monotonically increasing generation to serverless loads and
  reject an asynchronous completion unless it still owns the newest request.
  Online-domain navigation explicitly invalidates outstanding serverless
  requests, which otherwise had no replacement load call to advance ownership.
- Regression: source contracts require generation capture before send, stale
  rejection before parsing/state mutation, and online-navigation invalidation.
- Passed: world-loading failure/race contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: an obsolete download can still consume network/cache resources because
  the common request base has no cancellation API, but it can no longer import
  entities or replace session, permissions, connection, or commit state.
- Pico 4 validation: **not executed**. Rapidly alternate slow HTTP/ATP/local
  serverless targets and an online place; force completions out of order and
  verify only the final destination becomes visible/READY.

### 34 — Visible serverless load failures

- Branch: `nightly/pico4-34-serverless-load-error`
- Commit: `1d4a2a0689` (`Expose Pico serverless load failures`)
- Change: track file-open, request-creation, download, and parse failures for
  the current serverless destination and feed them into the Pico loading state
  as `WORLD_SERVER_UNAVAILABLE` instead of indefinitely reporting
  `RECEIVING_WORLD`. New serverless and online navigations clear the failure;
  stale requests cannot set it because generation rejection happens first.
- Regression: source contracts cover all failure classes, ordering behind the
  stale-generation guard, loading-state consumption, and navigation reset.
- Passed: world-loading failure/race contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: this changes only failure presentation and keeps the interstitial/input
  safety lock active; it does not guess a fallback destination or dismiss an
  invalid world automatically.
- Pico 4 validation: **not executed**. Attempt missing files, malformed JSON,
  denied/404/timeout URLs, then navigate to valid local/remote and online
  destinations; verify immediate failure status and clean recovery.

### 35 — Private restart entry point

- Branch: `nightly/pico4-35-private-restart-entrypoint`
- Commit: `2096887ef7` (`Protect Pico restart entry point`)
- Change: route scheduled restarts through a dedicated non-exported,
  no-history Activity which alone consumes the app-private one-shot argument
  handoff. The exported launcher no longer inspects any Intent extras or can be
  induced to consume pending restart state.
- Regression: manifest/source contracts require the restart Activity to be
  non-exported, the public launcher to ignore its Intent, and the private path
  to consume arguments and launch the internal Qt Activity.
- Passed: Android entry-point contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: normal launcher and permission-denied startup behavior are unchanged;
  scheduled restart now skips the permission trampoline because it originates
  from an already running process where optional microphone permission was
  already resolved.
- Pico 4 validation: **not executed**. Trigger render-scale restart with audio
  permission granted and denied, rotate/recreate around startup, launch the app
  externally during the 1.5-second handoff, and verify exactly one Qt Activity
  starts with the preserved arguments.

### 36 — OpenXR frame failure cleanup

- Branch: `nightly/pico4-36-openxr-frame-cleanup`
- Commit: `5ee4c778f7` (`Complete failed Pico OpenXR frames`)
- Change: after a successful `xrBeginFrame`, all acquire/wait/backend/index/
  release failures now best-effort release every successfully waited eye image
  and call `xrEndFrame` with zero layers. Wait uses OpenXR's infinite duration
  instead of a one-microsecond timeout; images from a failed wait are not
  illegally released. Stereo resource/index validation replaces a release-
  build null dereference, and present rate advances only after successful end.
- Regression: source contracts verify acquire-count ordering, common cleanup
  use by every failure class, empty-layer submission, resource/index guards,
  and success-only present accounting.
- Passed: OpenXR display cleanup contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: cleanup follows OpenXR's required acquire/release and begin/end pairing;
  runtime-specific recovery after a fatal session error still depends on the
  existing session state machine.
- Pico 4 validation: **not executed**. Inject/observe acquire, wait, release,
  context-loss and suspend/resume failures; verify no swapchain starvation,
  unmatched-frame validation errors, crash, or permanently frozen presentation.

### 37 — Fail-closed OpenXR present poses

- Branch: `nightly/pico4-37-openxr-present-pose`
- Commit: `a37bc97a50` (`Validate Pico OpenXR present poses`)
- Change: stop mutating the configured view count with `xrLocateViews` output;
  require exact counts plus position/orientation validity before using eye or
  stage views; validate optional projection storage; check `xrLocateSpace` and
  both head flags before replacing the last valid present pose. Projection
  submission now also requires both view position and orientation.
- Regression: OpenXR display contracts cover view counts/flags, storage,
  head-result/flag ordering, last-valid-pose preservation, and layer gating.
- Passed: OpenXR display contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: frames with partial tracking validity now submit no projection layer
  and retain the previous valid head pose instead of consuming undefined pose
  fields; recovery resumes automatically on the next fully valid locate.
- Pico 4 validation: **not executed**. Cover startup, guardian/tracking loss,
  headset removal, suspend/resume and runtime recenter; verify no pose jump,
  NaN view, stale rendered layer, crash, or failure to recover tracking.

### 38 — WebView JNI class-loader isolation

- Branch: `nightly/pico4-38-webview-jni-classloader`
- Commit: `5f973baace` (`Initialize Pico WebView JNI bridge`)
- Change: initialize the WebView native bridge from its Java class and retain a
  process-lifetime global class reference plus its own `JavaVM`. Qt-originated
  calls no longer depend on `FindClass` from a natively attached thread or on
  the unrelated OpenXR loader's VM lifecycle.
- Regression: bridge contracts require Activity initialization, transactional
  global-reference storage, own-VM attachment, and absence of both `FindClass`
  and the OpenXR VM accessor.
- Passed: WebView/JNI bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: the global class reference intentionally lives for process lifetime,
  matching the static native library and Java class; repeated Activity creation
  discards the redundant new reference without replacing the valid one.
- Pico 4 validation: **not executed**. Cold-start, recreate and restart the
  Activity, then create/destroy multiple Web entities from Qt worker/main
  contexts; verify bridge methods resolve without class-loader exceptions.

### 39 — Transactional WebView resize memory

- Branch: `nightly/pico4-39-webview-resize-memory`
- Commit: `26d2e2c70c` (`Harden Pico WebView frame allocation`)
- Change: allocate replacement Bitmap/Canvas/direct-buffer state before
  publishing it, retain the working old frame on allocation failure, explicitly
  recycle replaced/destroyed Bitmaps, and do not register a newly created
  WebView unless its initial frame allocation succeeds.
- Regression: bridge contracts verify allocation-before-publication, exception/
  OOM handling, old-bitmap recycling, pre-registration initial resize, and
  destruction cleanup.
- Passed: WebView/JNI bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: Canvas/direct-buffer objects remain GC-managed, while the large native
  Bitmap allocation is released deterministically; a failed live resize keeps
  rendering its previous valid dimensions until a later resize succeeds.
- Pico 4 validation: **not executed**. Rapidly resize and destroy multiple Web
  entities near the 2048-edge cap under memory pressure; confirm stable frames,
  bounded memory, no phantom instances, and recovery after allocation failure.

### 40 — WebView creation handshake

- Branch: `nightly/pico4-40-webview-creation-handshake`
- Commit: `23bed0c0b9` (`Confirm Pico WebView creation`)
- Change: distinguish native creation-pending from Java-confirmed creation;
  report Activity/provider/frame-allocation failures back through JNI; marshal
  results to the owning Qt thread with lifetime protection; and reapply current
  URL, User-Agent, background and dimensions after success so updates made
  during asynchronous creation cannot be lost. Transient failures receive up
  to three lifetime-bound delayed retries without an unbounded retry loop.
- Regression: bridge contracts reject eager-created state, require all Java
  completion paths and queued lifetime-safe native delivery, and verify full
  post-create property synchronization.
- Passed: WebView/JNI bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: failed creation remains uncreated rather than accepting input into a
  phantom Java instance; a later geometry/component attempt can retry. Normal
  creation adds one idempotent state synchronization round-trip.
- Pico 4 validation: **not executed**. Create entities during Activity startup,
  change URL/User-Agent/size/background before first frame, inject provider or
  allocation failure, then retry and verify the latest state is rendered.

### 41 — Native microphone frame alignment

- Branch: `nightly/pico4-41-audio-frame-alignment`
- Commit: `14cd847f55` (`Validate Pico microphone frame alignment`)
- Change: reject JNI PCM callbacks unless transport is configured and byte
  count is aligned to the current channel frame, before allocating/copying the
  Java array; recheck under enqueue lock; exclude invalid callbacks from the
  liveness watchdog while counting them as dropped; align every FIFO drain
  slice to the same frame boundary.
- Regression: source contracts cover validation-before-copy, configured/frame
  checks under lock, watchdog ordering, drop accounting and drain alignment.
- Passed: native audio transport contracts; audio JVM lifecycle/buffer tests;
  full `pico-device-free-test.sh`; `git diff --check`.
- Risk: Android PCM16 reads are normally frame-aligned, so valid capture is
  unchanged; corrupt partial samples/channels now drop as one callback instead
  of phase-shifting all subsequent audio.
- Pico 4 validation: **not executed**. Capture mono/stereo sources while forcing
  partial/error reads and rapid restart; verify invalid callbacks are dropped,
  watchdog recovery occurs, and later speech retains channel/sample alignment.

### 42 — Create QML message boundary

- Branch: `nightly/pico4-42-create-message-validation`
- Commit: `e5830827b5` (`Validate Pico Create QML messages`)
- Change: normalize the native Create page's QML messages before dispatch,
  reject missing/non-string methods and non-object parameters, and invoke only
  registered own button handlers. Invalid or stale UI messages can no longer
  terminate the long-running Create script through unchecked dereferences.
- Regression: executable Node tests cover malformed values, default parameters,
  valid Pico focus messages, validation-before-dispatch, and the registered
  handler guard.
- Passed: Create QML boundary tests; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: malformed messages are ignored with one diagnostic; all existing
  object-shaped QML messages and registered Create buttons retain their behavior.
- Pico 4 validation: **not executed**. Open/close Create repeatedly, exercise
  every native creation button and numeric focus control, then inject malformed
  and unknown QML messages and verify Create remains responsive.

### 43 — WebView startup retry coverage

- Branch: `nightly/pico4-43-webview-startup-retry`
- Commit: `32c97be53e` (`Retry Pico WebView startup failures`)
- Change: route missing JNI environments, Java-string allocation failures and
  synchronous bridge-call failures through the same bounded creation retry used
  for asynchronous Java failures. A Web entity completed before Activity bridge
  initialization can therefore recover without a later geometry mutation.
- Regression: WebView bridge contracts require all three synchronous failure
  paths to schedule the shared, lifetime-bound, capped retry helper.
- Passed: 13 WebView bridge tests; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: startup failures may emit up to three existing one-second retries; the
  item lifetime cancels timers and successful creation suppresses queued work.
- Pico 4 validation: **not executed**. Enter a world with Web entities during
  cold Activity startup, delay bridge/provider initialization, and verify pages
  appear after recovery without resizing or re-entering the world.

### 44 — OpenXR stereo view initialization

- Branch: `nightly/pico4-44-openxr-view-init`
- Commit: `6eb3b5a67c` (`Validate Pico OpenXR view initialization`)
- Change: require the Pico primary-stereo runtime to report exactly two views,
  reject a changed populated count and zero recommended dimensions/sample count,
  and publish view/swapchain storage only after all enumeration checks pass.
  Release builds no longer rely on an assertion before later fixed stereo access.
- Regression: OpenXR display contracts verify exact counts, configuration
  validation, publication ordering, and removal of the count assertion.
- Passed: 7 OpenXR display contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: an invalid/non-stereo OpenXR runtime now fails display initialization
  explicitly instead of continuing into out-of-bounds or zero-sized resources.
- Pico 4 validation: **not executed**. Cold-start on the Pico runtime, verify two
  valid eye views and normal rendering, then exercise runtime initialization
  failure/restart and confirm the client fails closed without a native crash.

### 45 — OpenXR swapchain initialization

- Branch: `nightly/pico4-45-openxr-swapchain-init`
- Commit: `747a00cd8e` (`Harden Pico OpenXR swapchain initialization`)
- Change: reject empty or changing swapchain-format/image enumerations before
  indexing storage, reject a missing chosen format, publish image arrays only
  after exact enumeration, and destroy all partial swapchains/foveation state on
  every later initialization failure and normal graphics uncustomization.
- Regression: OpenXR display contracts cover empty and changed counts,
  publication ordering, failure cleanup, handle nulling and teardown reuse.
- Passed: 9 OpenXR display contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: malformed/runtime-loss enumeration now aborts graphics initialization;
  valid Pico runtime counts are unchanged. Explicit swapchain teardown replaces
  relying on eventual parent-session destruction.
- Pico 4 validation: **not executed**. Repeatedly activate/deactivate and restart
  the OpenXR session; inject format/image enumeration and foveation failures and
  verify clean recovery without stale textures, handle growth or native crashes.

### 46 — Opt-in OpenXR latency tracing

- Branch: `nightly/pico4-46-openxr-latency-trace`
- Commit: `d3144dcef5` (`Gate Pico OpenXR latency tracing`)
- Change: read `debug.overte.latency_trace` once when creating the OpenXR context
  and run the per-second input/present clocks and info logs only for explicit
  `1`, `true`, or `on`. The trace format remains available for controlled tests.
- Regression: OpenXR display contracts verify the property parser and that both
  timestamp reads and both latency logs are downstream of the opt-in guard.
- Passed: 10 OpenXR display/lifecycle contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: normal sessions stop emitting unused periodic latency lines; controlled
  traces must explicitly enable the documented process-start property.
- Pico 4 validation: **not executed**. Compare normal and opt-in log capture;
  verify zero `PICO_LATENCY_*` lines by default and paired input/frame samples
  approximately once per second when the property is enabled before launch.

### 47 — OpenXR event-loss termination

- Branch: `nightly/pico4-47-openxr-event-loss`
- Commit: `d2d053b428` (`Stop Pico OpenXR event loss loops`)
- Change: stop the frame cycle and finish the current event iteration when the
  runtime reports instance loss, then reset and poll a fresh event buffer. The
  previous `continue` reprocessed the same successful buffer indefinitely.
  Render startup now also deactivates immediately when event polling fails.
- Regression: OpenXR contracts reject `continue` in the instance-loss case,
  require complete buffer reset/new polling, and verify render-loop propagation
  of a failed `pollEvents()` result.
- Passed: 12 OpenXR display/lifecycle contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: runtime/instance loss now exits or deactivates instead of spinning or
  allowing one more frame; normal event and render processing is unchanged.
- Pico 4 validation: **not executed**. Force Activity/runtime loss during active
  rendering and suspend/resume; verify prompt exit/deactivation, no frozen CPU
  loop, and a clean subsequent cold start.

### 48 — OpenXR EGL color configuration

- Branch: `nightly/pico4-48-openxr-egl-blue`
- Commit: `4073b102ba` (`Require Pico OpenXR EGL blue channel`)
- Change: request an 8-bit blue channel in both generic EGL and Android GLES
  OpenXR config selection. Both lists previously requested red twice and placed
  no constraint on blue, allowing a color-incompatible EGL config.
- Regression: OpenXR contracts require exactly one 8-bit red, green and blue
  attribute in each of the two session EGL configuration lists.
- Passed: 13 OpenXR display/lifecycle contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: the Pico's normal RGBA8-compatible config satisfies the corrected
  request; runtimes without an 8-bit RGB window config now fail selection rather
  than entering OpenXR with an incompatible framebuffer.
- Pico 4 validation: **not executed**. Cold-start OpenXR through both available
  EGL binding paths where possible and verify normal full-color rendering with
  no config-selection or graphics-device error.

### 49 — OpenXR reference-space initialization

- Branch: `nightly/pico4-49-openxr-reference-spaces`
- Commit: `e28a6006d9` (`Harden Pico OpenXR reference spaces`)
- Change: enumerate an exact, stable reference-space capability list before
  requiring Stage and View, reuse an already complete pair during graphics
  re-customization, and create both through local handles. View creation failure
  now destroys the unpublished Stage handle instead of leaving partial state.
- Regression: OpenXR contracts cover zero/changed capability counts, required
  types, local handles, rollback-before-publication and complete-pair reuse.
- Passed: 14 OpenXR display/lifecycle contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: runtimes without Stage space now fail explicitly; Pico supplies Stage
  and View. Existing complete spaces are retained across graphics customization.
- Pico 4 validation: **not executed**. Re-customize graphics and suspend/resume
  repeatedly; inject View-space creation failure and verify Stage rollback,
  clean recovery, stable tracking origin and no reference-space handle growth.

### 50 — Atomic OpenXR action initialization

- Branch: `nightly/pico4-50-openxr-action-init`
- Commit: identified by subject `Initialize Pico OpenXR actions atomically`; the
  exact hash is recorded by the following stacked task or final report.
- Change: initialize the action-set handle to null and treat every declared
  action as required by the keyed update path. Any action/pose-space or attach
  failure now clears unpublished wrappers, destroys the unattached action set,
  nulls its handle and reports failure instead of later throwing in `at()`.
- Regression: input contracts verify initialized handles, rollback/destroy,
  failure-before-map-publication and the identical attach-failure cleanup path.
- Passed: 8 OpenXR input contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: a runtime that cannot create a declared action now leaves controller
  state neutral and retries initialization rather than providing a partial map.
- Pico 4 validation: **not executed**. Inject action, pose-space and attach
  failures during controller startup; verify neutral input/no crash, then remove
  the fault and confirm both controllers initialize normally on retry.

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
- Entity List/import, mirror/secondary-camera, and remaining Create paths showed
  no additional narrow defect yet that could be responsibly changed within the
  available device-free evidence. Existing Pico code in these broad areas
  requires configured native builds and targeted runtime scenarios before
  behavioral changes.
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
