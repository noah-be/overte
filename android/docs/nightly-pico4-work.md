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
- Commit: identified by subject `Sanitize Pico tablet settings`; the exact hash
  is recorded by the following stacked task or final report.
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
