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
- Commit: `d37b52f47d` (`Initialize Pico OpenXR actions atomically`)
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

### 51 — OpenXR haptic boundary validation

- Branch: `nightly/pico4-51-openxr-haptic-validation`
- Commit: `d647c5164e` (`Validate Pico OpenXR haptic pulses`)
- Change: reject non-finite/non-positive or `XrDuration`-overflow durations
  before conversion while preserving fractional milliseconds, reject non-finite
  strength, require an active session and complete
  action map, use lookup instead of throwing `at()`, clamp the existing scaled
  amplitude to OpenXR's valid range, and return the actual apply result.
- Regression: input contracts cover every numeric/session/action guard,
  amplitude range and false propagation from failed haptic application.
- Passed: 8 OpenXR input contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: malformed or premature script pulses now return false; normal left/right
  finite positive pulses retain the prior `0.5 * strength` response until capped.
- Pico 4 validation: **not executed**. Pulse both controllers before/during/after
  session initialization, inject NaN/range/apply failures, and verify no crash,
  truthful results, bounded vibration and normal subsequent pulses.

### 52 — OpenXR binding path validation

- Branch: `nightly/pico4-52-openxr-binding-paths`
- Commit: `b4bd85c376` (`Validate Pico OpenXR binding paths`)
- Change: initialize and validate every suggested input-path conversion before
  adding it to a profile binding list. Remove unused `Action::getBindings()`,
  which ignored conversion results and incorrectly treated action IDs as paths.
- Regression: input contracts enforce convert/check/publish ordering, null-path
  initialization, explicit binding assignment and removal of the dead helper.
- Passed: 9 OpenXR input contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: a malformed binding path now rejects that controller profile cleanly;
  valid Pico interaction-profile paths and profile fallback remain unchanged.
- Pico 4 validation: **not executed**. Start with the Pico interaction profile,
  verify every mapped control and haptic output, then inject an invalid suggested
  path and confirm only that profile is rejected without stale/partial bindings.

### 53 — OpenXR hand-joint validity

- Branch: `nightly/pico4-53-openxr-hand-joints`
- Commit: `bc277f1d18` (`Validate Pico OpenXR hand joints`)
- Change: zero-initialize the hand-joint buffer, check the extension call and
  active state, and require valid position plus orientation on every joint before
  publishing any skeleton pose. Invalid samples leave the freshly cleared pose
  map neutral while capacitive controller finger hints remain available.
- Regression: input contracts enforce initialization and locate/result/active/
  flag validation ordering before the first hand pose-map write.
- Passed: 10 OpenXR input contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: partial hand skeletons are dropped as a unit rather than mixing stale or
  undefined joints; normal fully tracked Pico controller input is unaffected.
- Pico 4 validation: **not executed**. With hand tracking available, cover full
  hands, partial occlusion, tracking loss/recovery and controller fallback;
  verify no exploding joints, stale hand pose or interruption of touch hints.

### 54 — Microphone capture-thread startup

- Branch: `nightly/pico4-54-audio-thread-startup`
- Commit: `91e9c33ea1` (`Roll back Pico microphone thread startup`)
- Change: construct and start the capture thread through guarded phases after
  AudioRecord startup. Thread allocation/start failure now clears only the same
  published recorder/thread state, stops/releases the recorder and returns false.
  Capture priority uses the existing exception-contained priority helper.
- Regression: audio transport contracts verify create/publish/start/rollback/
  release ordering and prohibit an unguarded priority call in the capture loop.
- Passed: 6 native/Java audio transport contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: normal capture startup is unchanged; rare VM thread failures now unwind
  the already-started recorder rather than leaking a running phantom source.
- Pico 4 validation: **not executed**. Inject thread construction/start and
  priority failures, verify no live recorder/thread remains, then restart normal
  capture and confirm audio delivery and source switching recover.

### 55 — WebView asynchronous scroll lifetime

- Branch: `nightly/pico4-55-webview-scroll-lifetime`
- Commit: `7b19467441` (`Bind Pico WebView scroll callbacks`)
- Change: before refreshing layout from an asynchronous JavaScript scroll
  completion, require both an active instance and exact identity in the current
  handle map. A destroyed or same-handle replacement WebView is never touched by
  the old callback.
- Regression: WebView bridge contracts enforce callback/activity/map-identity/
  layout ordering inside the scroll path.
- Passed: 14 WebView bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: only stale callbacks skip layout; current scroll completions retain the
  forced software-WebView layout needed for updated frame delivery.
- Pico 4 validation: **not executed**. Scroll nested and document surfaces while
  rapidly destroying/recreating and navigating the same Web entity; verify no
  destroyed-view exception, cross-instance refresh or stale rendered frame.

### 56 — WebView creation exception handshake

- Branch: `nightly/pico4-56-webview-create-exceptions`
- Commit: `60bece6ed9` (`Complete Pico WebView creation failures`)
- Change: guard the complete main-thread WebView create/configure/settings/
  resize/register/load sequence, not only the constructor. Runtime or allocation
  failure cleans a registered/current view best-effort and always reports failed
  creation so the native bounded retry cannot remain permanently pending.
- Regression: WebView contracts verify constructor-through-navigation coverage,
  success-last ordering, broad exception handling, cleanup and failure callback.
- Passed: 15 WebView bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: successful creation behavior is unchanged; exceptional configuration or
  navigation now tears the partial view down and may enter the existing retries.
- Pico 4 validation: **not executed**. Inject provider, settings, buffer and
  `loadUrl` exceptions, verify one failure handshake/cleanup per attempt, then
  remove the fault and confirm bounded retry renders the latest entity state.

### 57 — WebView render-failure recovery

- Branch: `nightly/pico4-57-webview-render-recovery`
- Commit: `41b561140a` (`Recover Pico WebView frame failures`)
- Change: restore Canvas state in a `finally` block, catch frame draw/copy
  runtime/allocation failures, destroy the failed Java instance and report a
  failed creation result so native code uses its bounded retry. Normal frame
  scheduling now also requires the same active mapped instance.
- Regression: WebView contracts verify draw/restore/catch/cleanup/failure
  ordering and identity-guarded rescheduling.
- Passed: 16 WebView bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: an exceptional renderer is recreated instead of freezing its last frame;
  repeated hard failures stop after the native three-retry cap.
- Pico 4 validation: **not executed**. Inject Canvas draw and buffer-copy faults,
  destroy/replace during delivery, and verify cleanup plus bounded recovery with
  no frozen frame, callback storm or cross-instance scheduling.

### 58 — WebView best-effort destruction

- Branch: `nightly/pico4-58-webview-destroy-cleanup`
- Commit: `299b66d696` (`Complete Pico WebView destruction`)
- Change: isolate cancellation, frame-buffer disposal, load stop, blanking and
  final WebView destruction into individually guarded cleanup steps. A provider
  exception in one operation no longer skips later release work or aborts
  `destroyAll()` before other instances are processed.
- Regression: WebView contracts require every teardown operation to use the
  exception-contained helper and verify its RuntimeException boundary.
- Passed: 17 WebView bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: teardown exceptions remain logged, while cleanup continues best-effort;
  normal destruction order and active/map invalidation are unchanged.
- Pico 4 validation: **not executed**. Destroy several simultaneous Web entities
  while injecting failures at each cleanup stage; verify all instances disappear,
  later entities recreate, and no render/touch callback survives teardown.

### 59 — WebView transactional layout resize

- Branch: `nightly/pico4-59-webview-resize-layout`
- Commit: `9e9cd02ae1` (`Make Pico WebView resize transactional`)
- Change: perform density-scaled WebView measure/layout inside the guarded
  allocation phase before publishing new Bitmap/Canvas/buffer resources or
  recycling the working bitmap. Layout failure preserves the previous complete
  frame configuration and returns false to the existing caller diagnostics.
- Regression: WebView contracts require allocate/measure/layout ordering before
  resource assignment and retain allocation/layout exception cleanup coverage.
- Passed: 17 WebView bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: main-thread resize remains atomic from the renderer's perspective;
  successful dimensions and density scaling are unchanged.
- Pico 4 validation: **not executed**. Resize active pages repeatedly while
  injecting measure/layout exceptions and allocation pressure; verify the last
  valid frame persists and a later valid resize recovers without corruption.

### 60 — WebView asynchronous command recovery

- Branch: `nightly/pico4-60-webview-command-failures`
- Commit: `c226fcf722` (`Recover Pico WebView command failures`)
- Change: route navigation, background, User-Agent, resize, pointer and scroll
  UI-thread work through one Runtime/OOM boundary. Failures only invalidate the
  exact still-current instance, clean it up and report failed creation to enter
  the existing bounded native retry. Async scroll-layout completion uses the
  same identity-bound recovery.
- Regression: WebView contracts verify shared exception handling, identity
  checks, cleanup-before-retry, all six command call sites and scroll completion.
- Passed: 18 WebView bridge contracts; full `pico-device-free-test.sh`;
  `git diff --check`.
- Risk: exceptional commands recreate the page instead of escaping through the
  Android main looper; valid queued commands retain ordering on the same Handler.
- Pico 4 validation: **not executed**. Inject failures into each command and a
  delayed scroll-layout callback while replacing the same handle; verify only
  the current instance retries, without UI-thread crash or cross-page teardown.

### 61 — Microphone read-failure cleanup

- Branch: `nightly/pico4-61-audio-read-failure-cleanup`
- Commit: `30604a1f3c` (`Clean up failed Pico microphone reads`)
- Change: contain runtime exceptions from the blocking capture loop and use a
  `finally` ownership check to clear `running`, recorder and current-thread state
  only when the failing loop still owns the active recorder. That owner then
  stops/releases immediately; concurrent normal `stop()` remains the sole owner
  when it has already detached the recorder.
- Regression: audio transport contracts verify exception containment,
  identity-before-state-clear, locked single-owner claim and release ordering.
- Passed: 7 native/Java audio transport contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: unexpected reads no longer leave Java reporting a phantom active source;
  the native zero-callback watchdog still performs the subsequent restart.
- Pico 4 validation: **not executed**. Force negative reads and read exceptions
  while racing stop/source switch; verify exactly one release, neutral FIFO,
  watchdog restart and clean later capture without stale-source samples.

### 62 — Serialized microphone failure cleanup

- Branch: `nightly/pico4-62-audio-cleanup-serialization`
- Commit: `a5d649faed` (`Serialize Pico microphone failure cleanup`)
- Change: when an unexpectedly exiting capture loop still owns the current
  recorder, finish stop/release under the lifecycle lock before publishing the
  empty recorder slot. Concurrent `start()->stop()` either owns cleanup first or
  waits until release is complete, preventing old/new recorder overlap.
- Regression: audio contracts enforce running-stop/release/recorder-clear/thread-
  clear/claim ordering and verify release is inside the synchronized region.
- Passed: 7 native/Java audio transport contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: only failure cleanup holds the lock during release, after blocking read
  has already returned; normal explicit stop retains its existing join behavior.
- Pico 4 validation: **not executed**. Race forced read failure against rapid
  source restart; verify no simultaneous AudioRecord sessions, single release,
  bounded start delay and clean first samples from the replacement source.

### 63 — Activity instance lifecycle publication

- Branch: `nightly/pico4-63-activity-instance-lifecycle`
- Commit: `bd35077dd5` (`Retire Pico Activity before cleanup`)
- Change: publish the static Pico Activity reference as `volatile` for native/
  Java cross-thread restart access and clear the exact dying instance at the
  beginning of `onDestroy`, before WebView, microphone and OpenXR cleanup. New
  work can no longer bind to an Activity already being torn down.
- Regression: Android entry-point contracts require volatile publication and
  instance invalidation before each static/native resource cleanup.
- Passed: 5 Android entry-point/lifecycle contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: restart requests racing destruction now fail closed as unavailable;
  normal restart is scheduled before `finishAffinity()` and remains unchanged.
- Pico 4 validation: **not executed**. Race restart/Web entity creation against
  finish, recreation and process shutdown; verify no stale Activity use, leaked
  resource, missed normal restart or crash during cleanup.

### 64 — Transactional restart scheduling

- Branch: `nightly/pico4-64-restart-scheduling-failure`
- Commit: `22aeb6d2b4` (`Roll back failed Pico restart scheduling`)
- Change: guard PendingIntent/AlarmManager scheduling, fail closed when the
  service is absent, and synchronously clear private restart arguments on every
  scheduling exception before leaving the current Activity running. Consuming
  arguments now returns them only when their one-time removal commits.
- Regression: Android entry-point contracts cover null service, runtime failure,
  cleanup-before-return, explicit clear support and committed one-time consume.
- Passed: 6 Android entry-point/restart contracts; full
  `pico-device-free-test.sh`; `git diff --check`.
- Risk: a scheduling failure no longer kills the current process or leaves a
  later replayable handoff; normal successfully scheduled restarts are unchanged.
- Pico 4 validation: **not executed**. Deny exact alarms/remove AlarmManager and
  inject PendingIntent/set failures; verify the current session survives with no
  stale restart, then restore scheduling and confirm one successful relaunch.

### 65 — Owned OpenXR Activity references

- Branch: `nightly/pico4-65-openxr-activity-ref`
- Commit: `f0d5271243` (`Own Pico OpenXR Activity JNI references`)
- Change: serialize publication and teardown of the process-wide OpenXR loader
  state, replace the borrowed raw Activity accessor with an acquire operation
  that returns a caller-owned JNI global reference, and retain that reference
  across both `xrCreateInstance` and native restart scheduling. Activity
  destruction can no longer invalidate either consumer mid-call.
- Regression: loader contracts require mutex protection, owned global-reference
  acquisition and create-call lifetime; Android entry-point contracts verify
  acquire-after-attach and release-before-detach ordering for restart.
- Passed: 6 OpenXR loader/lifetime contracts; 7 Android entry-point/lifecycle
  contracts; full `pico-device-free-test.sh`; `git diff --check`.
- Risk: loader initialization is serialized with Activity teardown and may hold
  the small loader-state mutex during runtime initialization. Consumers now
  explicitly attach to JNI when necessary and release every acquired reference.
- Pico 4 validation: **not executed**. Recreate/finish the Activity while OpenXR
  instance creation and restart requests are in flight; verify no stale jobject,
  JNI warning, deadlock, missed normal restart, or leaked Activity reference.

### 66 — OpenXR post-graphics session rollback

- Branch: `nightly/pico4-66-openxr-session-rollback`
- Commit: `9e55e20f30` (`Roll back incomplete Pico OpenXR sessions`)
- Change: make post-graphics OpenXR initialization transactional across session
  and required reference-space creation. If Stage/View space setup fails, the
  newly created session is destroyed and its published handle cleared before
  returning failure, so a retry cannot inherit a half-initialized session.
- Regression: display/source contracts require session destruction and handle
  invalidation between reference-space failure and the failed return.
- Passed: 15 OpenXR display/context contracts; `git diff --check`.
- Risk: rollback failure is logged and the handle is still invalidated to fail
  closed; instance destruction remains the final runtime cleanup boundary.
- Pico 4 validation: **not executed**. Inject unsupported/failing Stage or View
  space creation, then retry activation; verify one session teardown, clean
  subsequent creation, no stale space use and normal successful rendering.

### 67 — Fail-closed OpenXR session transitions

- Branch: `nightly/pico4-67-openxr-transition-failclosed`
- Commit: `4d1b052038` (`Fail closed on Pico OpenXR transition errors`)
- Change: disable the frame cycle before beginning or ending a session, mark the
  context invalid when either runtime transition fails, and publish quit/
  non-rendering/invalid state before attempting loss-time destruction. Successful
  destruction now also clears the running-session flag.
- Regression: OpenXR context contracts verify state publication precedes begin,
  end and destroy calls and that each failure path invalidates rendering.
- Passed: 16 OpenXR display/context contracts; `git diff --check`.
- Risk: transition errors deliberately deactivate rendering instead of trying
  further frame calls against a runtime in an unknown state.
- Pico 4 validation: **not executed**. Inject begin/end/destroy failures during
  resume, pause and runtime loss; verify rendering stops immediately, no further
  frame calls occur, application shutdown remains bounded and clean resume still
  works when transitions succeed.

### 68 — Stale OpenXR session-event rejection

- Branch: `nightly/pico4-68-openxr-session-event`
- Commit: `27bdc7cbd8` (`Reject stale Pico OpenXR session events`)
- Change: validate the embedded session handle on state, interaction-profile and
  user-presence events before applying any state or querying the runtime. Events
  queued for a destroyed/replaced session, or received with no current session,
  are logged and ignored instead of mutating the current Pico session.
- Regression: OpenXR context contracts cover null/current handle checks before
  the first side effect of all three session-scoped event variants.
- Passed: 17 OpenXR display/context contracts; `git diff --check`.
- Risk: only events whose OpenXR session does not exactly match the current
  handle are dropped; instance-scoped loss handling is unchanged.
- Pico 4 validation: **not executed**. Rapidly pause/resume and recreate the
  OpenXR session while changing controller profile and headset presence; verify
  stale-event warnings cause no new-session teardown or incorrect mount/input
  state and current-session events still apply.

### 69 — Atomic hand-tracking function capability

- Branch: `nightly/pico4-69-openxr-hand-functions`
- Commit: `1d2265a8fc` (`Validate Pico OpenXR hand functions`)
- Change: require successful loading of all `XR_EXT_hand_tracking` entry points
  before advertising hand tracking to Pico input code. A missing Create, Destroy
  or Locate function now disables the capability and clears every partially
  loaded pointer instead of allowing a later null/partial dispatch.
- Regression: input/context contracts cover checked loading of all three entry
  points, atomic capability disablement and partial-pointer cleanup.
- Passed: 11 OpenXR input/fail-closed contracts; `git diff --check`.
- Risk: a runtime that advertises the system capability but omits an entry point
  loses skeletal hand input while normal controller input remains available.
- Pico 4 validation: **not executed**. Inject each missing entry point and verify
  controller input remains usable without a crash; with all functions present,
  verify both hand trackers still initialize and publish valid joints.

### 70 — Transactional hand-tracker publication

- Branch: `nightly/pico4-70-openxr-hand-publication`
- Commit: `e4555d0b34` (`Publish only valid Pico hand trackers`)
- Change: create each Pico hand tracker into a null-initialized candidate and
  publish it to the input device only after `xrCreateHandTrackerEXT` succeeds.
  A runtime failure can no longer leave a modified/invalid output handle that a
  later joint-location update mistakes for a usable tracker.
- Regression: input contracts require candidate creation, checked result before
  publication, no direct writes through member handles and independent setup of
  both hands.
- Passed: 12 OpenXR input/fail-closed contracts; `git diff --check`.
- Risk: one hand may remain available when the other tracker fails, matching the
  existing per-hand null-handle checks; no tracking thresholds were changed.
- Pico 4 validation: **not executed**. Inject left and right tracker creation
  failures separately; verify the failed hand stays neutral with no invalid-
  handle calls while the successful hand and controllers continue to work.

### 71 — Checked OpenXR debug-messenger lifecycle

- Branch: `nightly/pico4-71-openxr-debug-messenger`
- Commit: `4db0e8325a` (`Harden Pico OpenXR debug messenger`)
- Change: require both debug-utils Create and Destroy entry points before using
  the optional extension, publish a null-initialized messenger only after
  successful creation, and explicitly destroy it before its parent OpenXR
  instance. Missing optional functions now disable diagnostics without crashing.
- Regression: context contracts cover checked function loading, transactional
  handle publication and debug-messenger-before-instance destruction ordering.
- Passed: 18 OpenXR display/context contracts; `git diff --check`.
- Risk: validation diagnostics are unavailable when a runtime advertises an
  incomplete debug-utils extension; core rendering remains unaffected.
- Pico 4 validation: **not executed**. Run with validation/debug-utils enabled,
  inject missing/create-failing entry points, and verify bounded shutdown, no
  null dispatch, no leaked messenger and unchanged rendering without diagnostics.

### 72 — Atomic OpenXR controller user paths

- Branch: `nightly/pico4-72-openxr-user-paths`
- Commit: `b800036698` (`Validate Pico OpenXR controller paths`)
- Change: initialize both Pico hand user paths to `XR_NULL_PATH`, resolve them
  into local candidates with checked results, and publish neither until both
  required conversions succeed. Optional Vive-profile conversion is checked and
  published separately, so its absence cannot contaminate required input paths.
- Regression: input/context contracts cover null defaults, conversion/check/
  publication order for both hands and conditional optional-profile publication.
- Passed: 13 OpenXR input/fail-closed contracts; `git diff --check`.
- Risk: an invalid runtime path table now rejects OpenXR initialization instead
  of continuing with undefined action subpaths; this is intentional fail-closed
  behavior and does not alter valid Pico mappings.
- Pico 4 validation: **not executed**. Inject left/right path-conversion failures
  and verify clean startup rejection with no action creation; verify normal Pico
  controllers, profile changes and haptics when both paths resolve.

### 73 — Validated Pico display-refresh capability

- Branch: `nightly/pico4-73-openxr-refresh-capability`
- Commit: `93c2ff47d3` (`Validate Pico OpenXR refresh rates`)
- Change: atomically disable and clear the FB display-refresh capability when
  any required entry point is missing, reject empty or count-changing runtime
  enumerations, and select the existing lowest-rate policy only from finite,
  positive advertised values. No refresh-rate constant or tuning target changed.
- Regression: display/context contracts cover partial function loading, zero and
  changed counts, finite/positive filtering before the runtime request.
- Passed: 19 OpenXR display/context contracts; `git diff --check`.
- Risk: malformed refresh-rate data now skips the optional request and leaves
  runtime defaults active rather than issuing an invalid request.
- Pico 4 validation: **not executed**. Inject missing FB functions and malformed/
  changing rate lists; verify startup/rendering continues at runtime defaults.
  With Pico's normal 72/90 Hz list, verify the logged/requested mode remains 72 Hz.

### 74 — Quiet Android controller-key hot path

- Branch: `nightly/pico4-74-controller-key-logging`
- Commit: `7bdc0bd381` (`Remove Pico controller key hot-path logging`)
- Change: retain the deliberate consume-all behavior for Pico OS controller key
  duplicates, but remove per-event debug string construction/logging from the
  Android dispatch hot path. OpenXR remains the authoritative controller source
  and the existing opt-in transition/latency diagnostics remain available.
- Regression: Android entry-point contracts require immediate consumption while
  forbidding logging and key/action extraction within `dispatchKeyEvent`.
- Passed: 8 Android entry-point/lifecycle contracts; `git diff --check`.
- Risk: individual duplicate Android key codes are no longer visible in logcat;
  this path intentionally does not drive Overte input.
- Pico 4 validation: **not executed**. Hold/repeat every controller button while
  watching input latency and ANR behavior; verify OpenXR button transitions are
  unchanged and no `Consuming Android key event` log flood remains.

### 75 — Empty serverless navigation invalidation

- Branch: `nightly/pico4-75-world-load-generation`
- Commit: `8f9bdacaf1` (`Invalidate Pico world loads on empty navigation`)
- Change: treat an empty serverless destination as a request-generation boundary
  before returning. A pending HTTP/ATP scene load can no longer finish later and
  commit entities, permissions or session state after a reset/empty navigation.
- Regression: world-state contracts require generation advancement before the
  empty-URL early return in addition to existing stale-before-parse checks.
- Passed: 8 world-loading/failure-path contracts; `git diff --check`.
- Risk: empty navigation now retires outstanding scene requests but otherwise
  retains its previous no-load behavior.
- Pico 4 validation: **not executed**. Start a throttled remote serverless load,
  issue an empty/reset navigation before completion, and verify the late request
  is logged as stale with no entity/session/permission commit; retry normally.

### 76 — Restart URL argument isolation

- Branch: `nightly/pico4-76-restart-url-encoding`
- Commit: `3b5f8925c4` (`Encode Pico restart URL arguments`)
- Change: serialize a requested restart location through `QUrl`'s fully encoded
  form before appending it to Android's whitespace-delimited Qt application
  parameters. Spaces, tabs and other separators inside a URL can no longer split
  into additional command-line options during the private restart handoff.
- Regression: Android entry-point contracts require encoding before argument
  construction/handoff and forbid concatenating the raw URL.
- Passed: 9 Android entry-point/restart contracts; `git diff --check`.
- Risk: restart destinations are normalized to their percent-encoded form; URL
  semantics are preserved while malformed separator-bearing strings fail to
  become independent options.
- Pico 4 validation: **not executed**. Restart into locations containing spaces,
  Unicode, percent escapes, query/fragment data and option-like substrings;
  verify one destination argument, no injected flag and correct navigation.

### 77 — Fail-closed OpenXR frame termination

- Branch: `nightly/pico4-77-openxr-endframe-failclosed`
- Commit: `8b85424339` (`Fail closed after Pico xrEndFrame errors`)
- Change: when `xrEndFrame` fails after a successful begin, immediately disable
  the frame cycle and invalidate the OpenXR context. The next render tick can no
  longer enter another Wait/Begin sequence while runtime call-order state is
  unknown.
- Regression: display contracts require render disablement and context
  invalidation between the failed End result and return.
- Passed: 20 OpenXR display/frame contracts; `git diff --check`.
- Risk: an End failure now deactivates rendering instead of attempting an
  unsupported in-place recovery; normal successful presentation is unchanged.
- Pico 4 validation: **not executed**. Inject `xrEndFrame` failures for rendered,
  zero-layer and cleanup frames; verify no subsequent frame calls, prompt clean
  deactivation and normal presentation after a fresh application/session start.

### 78 — Fail-closed OpenXR frame start

- Branch: `nightly/pico4-78-openxr-frame-start-failclosed`
- Commit: `806666d112` (`Fail closed after Pico frame start errors`)
- Change: disable the render cycle and invalidate the context when either
  `xrWaitFrame` or `xrBeginFrame` fails. Frame-start errors can no longer produce
  an unbounded per-tick retry loop against a runtime with unknown call-order or
  session state; successful/positive OpenXR results retain existing behavior.
- Regression: display/context contracts require fail-closed state publication
  before returning from both Wait and Begin failure paths.
- Passed: 21 OpenXR display/frame contracts; `git diff --check`.
- Risk: transient runtime errors require a fresh activation/session instead of
  blind immediate retry, consistent with the existing poll/End fail-closed paths.
- Pico 4 validation: **not executed**. Inject Wait and Begin failures during
  focused, paused and resume transitions; verify no repeated frame calls/log
  storm and confirm clean rendering after a fresh application/session start.

### 79 — Null interaction-profile handling

- Branch: `nightly/pico4-79-openxr-profile-null`
- Commit: `133ed05970` (`Handle Pico controller profile loss`)
- Change: handle OpenXR's normal `XR_NULL_PATH` interaction-profile result as a
  disconnected/unbound controller after clearing the Vive pose compatibility
  flag, rather than passing the null path into `xrPathToString` and reporting a
  false critical runtime error.
- Regression: input/context contracts verify query, compatibility-state update,
  null check/continue and path conversion ordering.
- Passed: 14 OpenXR input/fail-closed contracts; `git diff --check`.
- Risk: profile loss is now an informational state rather than a conversion
  error; valid non-null profile diagnostics and mappings are unchanged.
- Pico 4 validation: **not executed**. Disconnect/reconnect and suspend/resume
  each controller; verify neutral input, no profile-path error flood, correct
  profile restoration and no stale Vive pose compatibility state.

### 80 — Explicit hand-tracker cleanup

- Branch: `nightly/pico4-80-openxr-hand-cleanup`
- Commit: `ef137567a8` (`Release Pico OpenXR hand trackers`)
- Change: give the Pico OpenXR input device an explicit destructor that releases
  every published hand tracker while its owning session and validated Destroy
  entry point remain available, then clears each handle regardless of runtime
  cleanup result. Null/implicitly session-destroyed handles remain safe no-ops.
- Regression: input contracts cover destructor declaration, synchronization,
  handle/session/function guards, destruction and unconditional invalidation.
- Passed: 15 OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: failed runtime destruction is logged while local handles are retired to
  prevent double cleanup; session/instance teardown remains the final fallback.
- Pico 4 validation: **not executed**. Enable both hands, deactivate/quit during
  active tracking and after runtime loss; verify exactly one Destroy per live
  tracker, no validation warnings, no leak and clean next-process tracking.

### 81 — Action pose-space ownership

- Branch: `nightly/pico4-81-openxr-action-space-cleanup`
- Commit: `6bd48e9a67` (`Release Pico OpenXR action spaces`)
- Change: tie each controller action's optional OpenXR pose-space handle to its
  C++ lifetime. Destruction now releases a live space while its session remains
  available and always clears the local handle, covering both normal teardown
  and partially completed action initialization.
- Regression: input contracts require null/session guards, `xrDestroySpace`
  before unconditional handle invalidation, and the declared Action destructor.
- Passed: 16 OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: after session loss, implicitly invalidated spaces skip runtime calls and
  are still cleared locally; active-session cleanup is explicit and logged.
- Pico 4 validation: **not executed**. Fail required action creation after one or
  more pose actions, then quit normally; verify each created pose space is
  released once, no validation leak/error and clean controller setup on restart.

### 82 — Complete OpenXR action-set cleanup

- Branch: `nightly/pico4-82-openxr-actionset-cleanup`
- Commit: `76fb640316` (`Release Pico OpenXR action sets`)
- Change: complete normal input teardown by clearing Action objects (and their
  pose spaces) before destroying the parent ActionSet, clearing its handle and
  retiring the initialized flag. Hand trackers remain the first session children
  released under the same device lock.
- Regression: input lifecycle contracts verify child collection cleanup before
  guarded ActionSet destruction, handle invalidation and state reset.
- Passed: 16 OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: ActionSet destruction errors are logged while the local handle is still
  invalidated to prevent a second destroy; instance teardown remains fallback.
- Pico 4 validation: **not executed**. Quit/deactivate after actions attach and
  after partial initialization/runtime loss; verify child-before-parent destroy
  ordering, no validation warning/leak and clean mappings after restart.

### 83 — Complete OpenXR context cleanup

- Branch: `nightly/pico4-83-openxr-context-cleanup`
- Commit: `a337a3e6e4` (`Release Pico OpenXR context children`)
- Change: explicitly destroy live View/Stage spaces and their parent Session
  before the debug messenger and OpenXR Instance during normal context teardown.
  All space/session handles and running/frame flags are invalidated even if a
  runtime cleanup call reports failure.
- Regression: context contracts verify child-to-parent destroy ordering through
  spaces, session, debug messenger and instance plus local state retirement.
- Passed: 22 OpenXR display/context lifecycle contracts; `git diff --check`.
- Risk: runtime-loss paths that already invalidated the session skip child calls
  and still clear stale local handles; active normal teardown becomes explicit.
- Pico 4 validation: **not executed**. Quit from focused, paused, pre-session and
  runtime-loss states under validation; verify each live handle is destroyed in
  order, shutdown is bounded and the next process creates a clean context.

### 84 — Deferred parent-session destruction

- Branch: `nightly/pico4-84-openxr-deferred-session-cleanup`
- Commit: `cddefe764b` (`Defer Pico OpenXR session destruction`)
- Change: on `LOSS_PENDING`/`EXITING`, immediately publish quit, non-rendering,
  invalid and non-running state but retain the Session handle for ordered owner
  teardown. The event handler no longer destroys the parent while swapchains,
  hand trackers, action spaces and ActionSet children are still live; their
  owners now release first and the Context destructor releases the Session.
- Regression: context contracts require fail-closed loss flags, forbid event-time
  Session destruction/handle clearing and require the ordered-teardown marker.
- Passed: 22 OpenXR display/context lifecycle contracts; `git diff --check`.
- Risk: parent destruction moves from event dispatch to immediate application
  shutdown ownership; `_shouldQuit` still prevents every further frame/input use.
- Pico 4 validation: **not executed**. Inject LOSS_PENDING and EXITING with live
  swapchains/controllers/hands; verify no further use, child-before-parent
  destruction under validation, bounded quit and clean next-process startup.

### 85 — Display swapchain destructor fallback

- Branch: `nightly/pico4-85-openxr-display-cleanup`
- Commit: `95da4740b8` (`Add Pico OpenXR display cleanup fallback`)
- Change: add an idempotent OpenXR display-plugin destructor that invokes the
  existing centralized foveation-profile/swapchain cleanup. Partial activation
  or shutdown paths that never reach `uncustomizeContext()` can no longer leave
  live display children for parent Session destruction.
- Regression: display contracts require the destructor fallback and confirm the
  shared cleanup null-checks and invalidates both profile and swapchain handles.
- Passed: 23 OpenXR display/context lifecycle contracts; `git diff --check`.
- Risk: normal uncustomization invokes the same cleanup first, making destructor
  fallback a no-op; runtime errors are logged and handles remain retired.
- Pico 4 validation: **not executed**. Abort during view/swapchain/foveation and
  layer initialization, then quit after normal rendering; verify one destruction
  per published child, no validation leaks and Session destruction occurs last.

### 86 — Capture-buffer allocation rollback

- Branch: `nightly/pico4-86-audio-buffer-allocation`
- Commit: `6d88c2a223` (`Contain Pico audio buffer allocation failure`)
- Change: move the microphone callback-buffer allocation inside the capture
  thread's protected `try/finally` and contain `OutOfMemoryError` alongside
  runtime read errors. Allocation failure now claims and releases the current
  AudioRecord exactly once and clears running/recorder/thread publication.
- Regression: native-audio source contracts require allocation inside the OOM
  catch/finally boundary and verify the existing ownership cleanup follows it.
- Passed: 8 audio transport/lifecycle contracts; `git diff --check`.
- Risk: severe allocation pressure now stops capture cleanly instead of leaving
  a permanently published silent recorder; ordinary capture is unchanged.
- Pico 4 validation: **not executed**. Inject callback-array OOM and restart
  capture; verify one stop/release, cleared state, no silent-stuck microphone and
  successful later source start after memory pressure is removed.

### 87 — Contained AudioRecord cleanup errors

- Branch: `nightly/pico4-87-audio-release-errors`
- Commit: `219aa543e7` (`Contain Pico AudioRecord cleanup errors`)
- Change: independently contain RuntimeExceptions from AudioRecord stop and
  release during explicit shutdown and startup/capture-loop rollback. A vendor
  driver failure can no longer skip thread joining, subsequent release attempts,
  capture-state retirement or the rest of Activity resource teardown.
- Regression: audio lifecycle contracts require guarded stop, join and guarded
  release ordering in both public stop and shared rollback helper.
- Passed: 9 audio transport/lifecycle contracts; `git diff --check`.
- Risk: driver cleanup failures are logged and shutdown continues; hardware that
  actually refuses release still relies on Android process cleanup.
- Pico 4 validation: **not executed**. Inject stop and release exceptions during
  source switch, read failure and Activity destruction; verify state clears,
  remaining cleanup runs, restart stays bounded and later capture can recover.

### 88 — Isolated Activity resource teardown

- Branch: `nightly/pico4-88-activity-cleanup-isolation`
- Commit: `a39d1667c1` (`Isolate Pico Activity cleanup failures`)
- Change: run WebView, microphone and OpenXR-Activity cleanup as independently
  contained shutdown steps after retiring the global Activity instance, and put
  Android's superclass destruction in `finally`. One component's Runtime/OOM
  failure can no longer prevent the remaining resource owners from cleaning up.
- Regression: Android lifecycle contracts cover owner order, shared exception
  containment and guaranteed `super.onDestroy()` execution.
- Passed: 9 Android entry-point/lifecycle contracts; `git diff --check`.
- Risk: severe cleanup failures are logged and teardown proceeds; resources a
  failing owner cannot release still fall back to process destruction.
- Pico 4 validation: **not executed**. Inject failure independently in WebView,
  AudioRecord and OpenXR Activity cleanup; verify later owners and superclass
  always execute, no stale Activity publication and bounded finish/restart.

### 89 — WebView creation queue rejection

- Branch: `nightly/pico4-89-webview-post-failure`
- Commit: `a61adfa3a1` (`Report Pico WebView queue rejection`)
- Change: check Android main-Handler acceptance for both the WebView creation
  job and its first frame. A quitting/dead Looper now completes the native
  creation handshake with failure, and a rejected first frame destroys the
  partially published Java instance before reporting failure.
- Regression: 19 WebView bridge/lifecycle contracts require checked outer/first-
  frame posts, cleanup and failure callbacks in their exact ordering.
- Passed: targeted 19-contract WebView suite; `git diff --check`.
- Risk: Looper shutdown now consumes one bounded native creation retry instead
  of leaving `_webViewCreationPending` stuck indefinitely.
- Pico 4 validation: **not executed**. Create Web entities while finishing/
  recreating the Activity and shutting down the Looper; verify bounded failure,
  no pending-stuck item, no Java instance leak and normal retry after recreation.

### 90 — WebView command/render queue rejection

- Branch: `nightly/pico4-90-webview-queue-lifecycle`
- Commit: `aa8984851f` (`Retire Pico WebViews on queue shutdown`)
- Change: check main-Handler acceptance for all post-creation commands and each
  delayed render tick. A dead/quitting Looper now reports native failure; rejected
  render rescheduling additionally removes and destroys the current Java instance
  instead of leaving C++ with a permanently created but frozen surface.
- Regression: 20 WebView bridge/lifecycle contracts cover command-post rejection
  and render-post rejection cleanup/callback ordering.
- Passed: targeted 20-contract WebView suite; `git diff --check`.
- Risk: queue shutdown triggers bounded native retry/retirement; commands for a
  handle already absent from the live map remain no-ops when successfully queued.
- Pico 4 validation: **not executed**. Navigate, resize, scroll and render while
  terminating/recreating the Activity Looper; verify no frozen created surface,
  bounded retries, cleanup of the old instance and recovery on the new Activity.

### 91 — Serialized microphone lifecycle transactions

- Branch: `nightly/pico4-91-audio-lifecycle-serialization`
- Commit: `006c29c0cd` (`Serialize Pico microphone lifecycle`)
- Change: serialize complete public AudioRecord start and stop transactions at
  the Java class monitor while retaining the short internal state lock for the
  capture thread. Concurrent source/lifecycle starts can no longer both create
  recorders and overwrite ownership, leaking the displaced live session.
- Regression: 10 audio transport/lifecycle contracts require synchronized public
  boundaries and stop-before-create-before-publication ordering.
- Passed: targeted 10-contract audio suite; `git diff --check`.
- Risk: concurrent lifecycle callers now wait for the active bounded stop/join;
  normal AudioClient-thread switching is already sequential and unchanged.
- Pico 4 validation: **not executed**. Race multiple source starts, Activity stop
  and capture failure; verify at most one AudioRecord, one owner/release per
  generation, bounded callers and clean PCM from the final requested source.

### 92 — Atomic XDev function capability

- Branch: `nightly/pico4-92-openxr-xdev-functions`
- Commit: `79d7c61006` (`Validate Pico OpenXR XDev functions`)
- Change: require successful loading of every MNDX XDev entry point actually
  used by Pico's OpenXR input fork before enabling optional body-tracker setup.
  Missing functions disable the capability and clear all partial pointers; the
  unused generation function is no longer needlessly resolved.
- Regression: 17 input/context contracts cover checked loading and cleanup for
  CreateList, Enumerate, GetProperties, DestroyList and CreateSpace.
- Passed: targeted 17-contract OpenXR input suite; `git diff --check`.
- Risk: incomplete optional XDev runtimes lose body trackers while controller/
  hand input remains available; normal Pico runtimes without MNDX are unchanged.
- Pico 4 validation: **not executed**. Inject each missing XDev entry point and
  verify clean capability disablement/no null dispatch; if a compatible tracker
  runtime is available, verify unchanged enumeration and tracking.

### 93 — Transactional XDev enumeration

- Branch: `nightly/pico4-93-openxr-xdev-enumeration`
- Commit: `e56830126b` (`Harden Pico OpenXR XDev enumeration`)
- Change: initialize/check the temporary XDev list, bound returned IDs to the
  supplied capacity, require valid properties and space capability, and publish
  each null-initialized candidate space only after successful creation. The
  temporary list is explicitly destroyed after every successful list creation.
- Regression: 18 input/context contracts cover list/enumeration/property checks,
  count bound, candidate-before-publication and list cleanup ordering.
- Passed: targeted 18-contract OpenXR input suite; `git diff --check`.
- Risk: malformed or partially failing optional trackers are skipped instead of
  entering the pose map with undefined handles; core Pico input is unchanged.
- Pico 4 validation: **not executed**. Inject CreateList, overflow, property and
  CreateSpace failures; verify no invalid calls/handles, one list destroy and
  valid trackers still enumerate independently where supported.

### 94 — XDev space ownership cleanup

- Branch: `nightly/pico4-94-openxr-xdev-cleanup`
- Commit: `25b9082158` (`Release Pico OpenXR XDev spaces`)
- Change: explicitly destroy every published optional XDev tracker space while
  its Session remains live, invalidate each handle and clear the tracker map
  before Action pose spaces and their parent ActionSet are released.
- Regression: input lifecycle contracts cover guarded XDev space destruction,
  per-handle/map invalidation and ordering before action cleanup.
- Passed: 18 OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: spaces implicitly invalidated by runtime loss skip calls and are cleared;
  active-session shutdown now owns them explicitly.
- Pico 4 validation: **not executed**. With compatible optional body trackers,
  quit during active tracking and after runtime loss; verify one destroy per
  space, no validation leaks and clean enumeration after restart.

### 95 — Vive Tracker function capability validation

- Branch: `nightly/pico4-95-openxr-vive-functions`
- Commit: `b2ee6792ff` (`Validate Pico OpenXR Vive Tracker function`)
- Change: enable HTC Vive Tracker interaction only when its required enumeration
  function resolves successfully. A loader/runtime mismatch now disables that
  optional path, clears its pointer and retains the XDev fallback instead of
  exposing a later null call and suppressing the usable tracker backend.
- Regression: the input/context contract verifies checked symbol loading,
  fallback selection ordering, capability disablement and pointer clearing.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: affects only optional body-tracker backend selection when an advertised
  extension is incomplete; Pico controller and hand input remain unchanged.
- Pico 4 validation: **not executed**. On a runtime with HTCX and/or MNDX tracker
  extensions, test complete and deliberately missing HTCX function exposure;
  verify HTCX wins only when callable and MNDX remains available otherwise.

### 96 — Body-tracker pose validity

- Branch: `nightly/pico4-96-openxr-tracker-poses`
- Commit: `a9ccd41fce` (`Reject invalid Pico body tracker poses`)
- Change: refuse XDev role inference before a predicted frame time exists, skip
  failed or incompletely tracked stage/local/head locations, and guard the head-
  height normalization denominator. Both HTCX and XDev publication now require
  valid position as well as orientation because both values feed each pose.
- Regression: input contracts cover time-before-locate ordering, all result and
  location-validity guards, division-after-height-check, and complete pose flags
  for both optional body-tracker backends.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: partially valid tracker samples are omitted for that update instead of
  emitting undefined translations; no calibration thresholds were changed.
- Pico 4 validation: **not executed**. During body-tracker calibration and use,
  inject no-frame-time, locate failure, orientation-only, position-only and zero-
  height samples; verify no role/pose publication until a complete sample arrives.

### 97 — XDev uncalibration state reset

- Branch: `nightly/pico4-97-openxr-tracker-uncalibrate`
- Commit: `90b2a71f1c` (`Reset Pico XDev roles on uncalibrate`)
- Change: mutate stored XDev trackers by reference when clearing inferred pose
  channels. Previously `uncalibrate()` reset only temporary copies, leaving stale
  foot/hip/chest roles active after calibration data was cleared.
- Regression: the input lifecycle contract requires reference iteration and
  verifies role, calibration-map and pending-calibration reset ordering.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: deliberately removes stale optional body-tracker role assignments when
  the user requests uncalibration; controller and hand mappings are untouched.
- Pico 4 validation: **not executed**. Calibrate XDev trackers, uncalibrate, move
  each tracker and verify no old body channel updates until calibration is run
  again; then verify roles are assigned from the new placement.

### 98 — OpenXR calibration setting validation

- Branch: `nightly/pico4-98-openxr-calibration-settings`
- Commit: `8d664ed520` (`Validate Pico OpenXR calibration settings`)
- Change: deserialize persisted `[x,y,z,w]` quaternions in GLM's required
  `(w,x,y,z)` constructor order, reject wrong-size/non-numeric/non-finite arrays
  and zero-length rotations, then normalize accepted rotations. The shared
  desktop OpenXR copy is kept format-compatible with Pico settings.
- Regression: input contracts enforce identical Pico/desktop array validation,
  constructor order, norm guard, normalization and serializer order.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: malformed or historically misread calibration entries are skipped; valid
  stored settings now round-trip to the rotation that was originally serialized.
- Pico 4 validation: **not executed**. Save a non-identity tracker calibration,
  restart and compare pose alignment; inject truncated, string, non-finite and
  zero-quaternion settings and verify they are ignored without corrupting poses.

### 99 — Pending body-tracker calibration

- Branch: `nightly/pico4-99-openxr-calibration-pending`
- Commit: `199afc9a06` (`Retain Pico tracker calibration until valid`)
- Change: retain a requested tracker calibration until at least one valid body
  pose is available, rather than consuming it unconditionally after one frame.
  Lookups no longer insert empty poses into the transient map. The shared desktop
  OpenXR implementation follows the same calibration-state contract.
- Regression: Pico/desktop input contracts verify non-inserting lookup, missing
  and invalid sample guards, publication-before-success and pending-state logic.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: a request made with no active body tracker remains pending and will apply
  once a valid tracker appears; explicit uncalibration still cancels it.
- Pico 4 validation: **not executed**. Request calibration before tracking begins
  and during tracking loss, then restore a valid tracker; verify exactly the first
  valid update completes calibration and uncalibrate cancels a pending request.

### 100 — Pending XDev role-inference retry

- Branch: `nightly/pico4-100-openxr-role-retry`
- Commit: `d846fc65ba` (`Retry Pico XDev roles while calibration waits`)
- Change: move XDev role inference from the one-shot calibration request into the
  input-mapper-locked update path and retry it only while calibration is pending.
  A request made before predicted frame time or valid tracker locations can now
  complete when those inputs arrive. The shared desktop path remains equivalent.
- Regression: Pico/desktop contracts require the request to be side-effect-free
  beyond state setup and enforce pending/backend guards plus inference-before-
  pose-update ordering inside the input mapper lock.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: pending XDev calibration performs three extra locate calls per tracker per
  frame until one valid mapped pose completes it; uncalibrate cancels the retry.
- Pico 4 validation: **not executed**. Request before session readiness and across
  tracking loss, then restore tracker/head locations; verify automatic completion,
  stable inferred roles and no retry calls after completion or cancellation.

### 101 — XDev role-inference stale-state reset

- Branch: `nightly/pico4-101-openxr-role-reset`
- Commit: `29cd9ffc59` (`Clear stale Pico XDev roles before inference`)
- Change: clear every prior XDev pose-channel assignment before a new role-
  inference pass, after confirming frame time is available. Failed/incomplete
  locations and trackers outside defined role bands can no longer retain an old
  foot/hip/chest role and prematurely complete recalibration. The shared desktop
  path receives the same result/location/height guards because Task 100 made its
  inference retry from the common update contract as well.
- Regression: Pico/desktop input contracts enforce time guard, reference-based
  role clearing, complete location checks, height guard and assignment ordering.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: a failed inference pass temporarily leaves optional XDev trackers
  unmapped, which is safer than publishing them through stale body channels.
- Pico 4 validation: **not executed**. Calibrate, move trackers between role bands,
  trigger recalibration and inject one failed locate; verify old channels go
  neutral and only currently classified trackers resume publication.

### 102 — Controller pose completeness

- Branch: `nightly/pico4-102-openxr-controller-pose-validity`
- Commit: `b13fa0e0b2` (`Reject incomplete Pico controller poses`)
- Change: require both valid position and orientation before counting or
  publishing an OpenXR controller pose, matching the data actually consumed.
  The common controller/body pose flag is applied identically in the Pico and
  shared desktop OpenXR implementations.
- Regression: Pico/desktop contracts enforce complete flags before tracked-count
  increment and before reading the controller translation.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: orientation-only samples now produce a neutral controller pose for that
  frame rather than a pose containing an invalid position.
- Pico 4 validation: **not executed**. Inject orientation-only and position-only
  grip/palm samples during tracking loss; verify controller count and hand pose go
  neutral, then recover on the first complete sample without stale interaction.

### 103 — Palm-to-grip pose fallback

- Branch: `nightly/pico4-103-openxr-palm-fallback`
- Commit: `37f60563cd` (`Fall back from incomplete Pico palm poses`)
- Change: choose palm input only from the complete pose sample actually consumed,
  rather than a separate action-active query, and fall back to grip within the
  same frame when palm is inactive or incomplete. Initialize the candidate pose
  fail-closed. Pico and shared desktop OpenXR selection remain equivalent.
- Regression: Pico/desktop contracts verify initialization, palm completeness,
  selection, fallback grip lookup and final validity ordering without the split
  `isPoseActive()` decision.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: a transiently incomplete palm pose now uses the valid grip pose and its
  existing grip offset instead of dropping the controller for that frame.
- Pico 4 validation: **not executed**. Alternate palm support/active state and
  inject incomplete palm samples while grip stays valid; verify continuous pose,
  correct offset selection, then clean return to palm on a complete sample.

### 104 — Dead split pose-activity query removal

- Branch: `nightly/pico4-104-openxr-dead-pose-query`
- Commit: `baf7be9538` (`Remove dead Pico OpenXR pose query`)
- Change: remove the now-unreferenced `Action::isPoseActive()` declaration and
  implementation from Pico and shared desktop OpenXR. Palm/grip selection has one
  checked `getPose()` source instead of retaining a divergent second state query.
- Regression: the input contract requires the dead API to remain absent from
  both sources/headers while retaining the pose-location API.
- Passed: targeted OpenXR input/lifecycle contracts; `git diff --check`.
- Risk: none for callers; repository-wide search confirmed no references after
  the Task 103 selection rewrite.
- Pico 4 validation: **not executed**. Covered by Task 103 palm/grip transition
  validation; confirm no additional action-state query appears in an API trace.

### 105 — Serialized serverless world transitions

- Branch: `nightly/pico4-105-serverless-reentrant-load`
- Commit: `96cac3b01d` (`Serialize Pico serverless world transitions`)
- Change: prevent local serverless imports from recursively restarting while
  `sendEntities()` processes nested Qt events; defer a genuinely different local
  destination until the current synchronous import unwinds. Replace the resettable
  loading timestamp used as a startup guard with a monotonic initial-handoff flag.
  Atomically publish commit/ready state for deterministic tests. The world-loading
  runner now waits for the initial handoff, proves the requested local filename
  committed, accepts legitimate missing serverless domain/world milestones, and
  retains navigation diagnostics on failure.
- Regression: nine world-state source contracts cover in-progress ordering,
  same-target suppression, deferred target storage, queued completion, atomic
  status publication and the monotonic handoff guard. The complete device-free
  Pico suite passes.
- Passed: full ARM64 debug APK build; update install; USB cold-start handoff;
  USB default-to-original local navigation (commit after 7 s, process alive);
  WLAN world-loading run to the aggressive fixture (playable 4,825 ms, overlay
  release 5,428 ms, zero domain resets); `git diff --check`.
- Known result: the original fixture committed but did not complete its full
  measured handoff within 60 s under its resource/script load. The aggressive
  fixture completed, but did not reach five uninterrupted quiet seconds during
  the configured 20 s post-load observation.
- Risk: multiple different local navigations arriving during one synchronous
  import collapse to the last deferred URL. This is intentional newest-target
  behavior, but rapid physical navigation still needs observation.
- Pico 4 validation: **executed without wearing or operating the headset** for
  startup, local navigation, process survival, milestone ordering and state
  restoration. Visual correctness and physical controller behavior were
  **not executed**.

### 106 — Unattended Pico 4 device validation record

- Branch: `nightly/pico4-106-device-validation-report`
- Commit: identified by subject `Document unattended Pico device validation`;
  the exact hash is recorded in the final report.
- Change: record the device-backed validation completed after Tasks 95–105 and
  replace the obsolete dependency/build blocker notes with measured results.
- Passed: Pico toolchain doctor; checksum-verified dependency setup; complete
  ARM64 debug build (41 Gradle tasks); repeated incremental builds; update APK
  installation; OpenXR instance/session startup; Pico 4 controller interaction
  profile detection; 72 Hz local-scene rendering; local avatar template toggle;
  replica target 0→5→0; five consecutive force-stop/cold-start lifecycle cycles
  with no matching fatal event; AudioRecord `VOICE_COMMUNICATION`,
  `VOICE_RECOGNITION`, `MIC` and `CAMCORDER` source selection at 48 kHz mono with
  continuous capture/processing, zero dropped frames and zero final backlog;
  automatic fan and brightness restoration; USB ADB restoration after WLAN tests.
- Additional passed tests after the navigation fix: online `overte_hub` connect
  and exact spawn verification; a 10 s conservative unattended locomotion run
  with automatic spawn/collision preflight and return; a 30 s Simpleperf capture
  after 10 s warm-up; received-avatar matrix stages 0→5→0, including five loaded
  replicas and return to one received avatar.
- Failed/limited: online `overte_hub` navigation initially remained disconnected
  and locomotion was safely cancelled before motion while the resettable startup
  guard still rejected navigation; both paths passed after Task 105. In the
  serverless scene, replica targets were
  accepted but replicas were not populated until the online Hub navigation was
  repaired. Initial short microphone runs exposed startup-dependent missing gate
  telemetry; 15 s retries passed all four sources. The avatar matrix's final
  repeated five-replica stage missed its warm-up status after the prior three
  stages passed; cleanup and explicit zero-replica restoration passed. The
  graphics matrix remained fail-closed because its required Hub reference PNG is
  absent. No audio sample was retained and no subjective quality claim is made.
- Risk: device execution confirms state transitions and telemetry, not perceived
  image quality, comfort, controller alignment, microphone quality, AEC or echo.
- Pico 4 validation: **executed without wearing or manually operating the
  headset**. Physical controller, visual and subjective audio checks remain
  **not executed**.

### 107 — Local object-interaction latency and controls

- Branch: `nightly/pico4-107-near-grab-timeline`
- Commit: identified by subject `Optimize Pico local object interaction`; the
  exact hash is recorded in the final session report.
- Change: add opt-in transition tracing for trigger/Grip, dispatcher, pointer,
  Near Grab and Far Grab edges, then use the captures to separate diagnostic
  overhead from the production interaction path. Simple unparented local Far
  Grab fixtures now follow the real controller joint directly through a
  fail-closed local fast path and restore their original parent and transform on
  release. A separate 60 Hz worker performs bounded thumbstick depth updates
  through a new local-entity-only native position API. Release edges terminate
  active Near/Far grabs immediately. Central validated Pico thresholds drive
  both grab decisions and the white/green/purple world-ray states and are
  exposed on a Pico-only Settings page. The lightweight fixture station loads
  for the local acceptance world without enabling diagnostics.
- Passed: JavaScript syntax for every changed runtime script; expanded Pico
  interaction regression; complete `android/tests/pico-device-free-test.sh`;
  full ARM64 debug APK build (`41` Gradle tasks, `BUILD SUCCESSFUL`); update APK
  installation and unattended cold start on Pico 4. The packaged app reached
  the local scene, created all four fixtures, started the independent Far Grab
  worker, stabilized at the requested `72/72` runtime FPS, and emitted no
  matching fatal, JavaScript, JNI or OpenXR startup error. Final diff checks are
  recorded in the session report.
- Measured result: verbose 20 Hz fixture/dispatcher instrumentation caused
  whole-client locomotion, tablet and interaction stutter and was removed from
  automatic startup. With production diagnostics disabled, the tester confirmed
  smooth global behavior, immediate Near Grab release, near-real-time local Far
  Grab controller following, and smooth continuous thumbstick depth adjustment.
  White at `0.10`, green at `0.50`, and purple at the shared `0.90` grab
  threshold were distinguishable; a fast press now advances to purple without
  waiting for entity initialization.
- Risk: the native fast update is deliberately limited to local entities.
  Domain/avatar entities retain their established network/physics paths. The
  worker's render-state update applies only to world pointers, not tablet/HUD
  pointers. Optional tracing can still perturb timing and must be stopped for
  production comparisons.
- Pico 4 validation: **executed manually** for the bundled red local Near Grab
  fixture and blue local Far Grab fixture: acquisition/release, lateral
  following, rapid controller movement, depth adjustment and three laser states
  passed to the tester's stated acceptance level. Tracking loss, off-hand
  rotation, both hands, domain-hosted entities and long-duration interaction
  were **not executed**. No thermal or quantitative motion-to-photon claim is
  made.

## Deferred, rejected, or blocked ideas

- Full `scriptURL`, Qt WebChannel, and bidirectional `EventBridge` emulation for
  Android WebView was not implemented. It defines a page-to-native security
  boundary and compatibility API that needs a reviewed protocol, origin/frame
  policy, Android integration build, and real page acceptance tests. A partial
  JavaScript interface would be less safe than the documented limitation.
- Tablet/HUD Web surfaces remain separate from the Pico world-Web-entity
  bridge, as established by the renderer audit. Replacing them would expand
  scope and risk already working UI paths.
- Remaining ray offsets, visual alpha quality, audio quality/AEC, thermal
  behavior, and render parameters were not tuned without corresponding
  measurements. Local fixture interaction latency was improved and manually
  accepted in Task 107, but no quantitative motion-to-photon result is claimed.
- Off-hand rotation was not reimplemented because Pico already inherits the
  desktop mapping. Only the inaccurate validation status was corrected.
- Entity List/import, mirror/secondary-camera, and remaining Create paths showed
  no additional narrow defect yet that could be responsibly changed within the
  available device-free evidence. Existing Pico code in these broad areas
  requires configured native builds and targeted runtime scenarios before
  behavioral changes.
- Native Qt/C++ host suites remain unavailable because `build-tests` has no
  configured `CMakeCache.txt`. Pico Android dependencies were subsequently
  restored through the documented setup path and full/incremental ARM64 builds
  passed; Android compilation is no longer blocked.

## Possible next steps

These are follow-up candidates, not known merge-blocking regressions:

1. Configure a separate native host-test build tree and run its Qt/C++ suites;
   the Android Java/JNI/C++ client already builds and packages successfully.
2. Design and review the WebChannel/EventBridge security and compatibility
   contract before implementing `scriptURL` or page-to-entity messaging.
3. Execute the remaining worn/manual headset checks below and use opt-in edge
   traces only when needed; measure before changing pose offsets or performance
   parameters.
4. Investigate the broad Create, avatar/camera, and reconnect areas only from a
   reproducible failing scenario or a new device-free unit seam.
5. Run unattended lifecycle follow-ups: repeated cold starts, serverless/online
   navigation, Activity suspend/resume where ADB can exercise it, sustained
   microphone telemetry, WebView/JNI error-log checks, and clean-production CPU
   profiling.

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
