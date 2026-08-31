# Touch device validation

This matrix is the release checklist for Overte's universal touch UI. Host
tests validate deterministic policy and component behavior; the rows below
cover Android/Qt/IME/GPU behavior that only a real runtime can expose. Record
the APK digest and an anonymized device class, not a serial, account, URL,
domain, manufacturer, model or raw log.

## Preconditions

- Build one Phone APK from the revision under test and pass the package gate.
- Enable gesture navigation for the first run and three-button navigation for
  the second system-navigation pass.
- Use a neutral local destination and test account. Do not put credentials or
  private destinations in reports.
- Run the automated lifecycle smoke before manual interaction:

  ```bash
  ANDROID_SERIAL=<serial> android/phone/tests/phone-device-test.sh <apk>
  ```

- Run performance sampling only on an explicitly selected non-VR physical
  device. Keep reports outside the worktree:

  ```bash
  ANDROID_SERIAL=<serial> PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
    PHONE_BENCHMARK_REPORT=<private-report-directory> \
    android/phone/tests/phone-graphics-benchmark.sh 120
  ```

## Device and posture matrix

| Class | Required configurations | Primary risk |
| --- | --- | --- |
| Compact phone | Portrait and landscape; 360–599 logical px usable width | Reflow, keyboard coverage, minimum targets |
| Large phone | Portrait and landscape; gesture and three-button navigation | Insets, action-bar placement, scale bounds |
| Cutout phone | Left/right asymmetric landscape cutout and portrait cutout | Independent safe edges, no centering drift |
| Tablet | Portrait, landscape and split-screen | Expanded grids, bounded content scale, resizing |
| Foldable | Folded, unfolded and posture transition while UI is open | Surface replacement, transient invalid metrics, focus retention |
| Freeform/multi-window | Narrow, medium and expanded live window resize | Width-class changes without restart or stale geometry |
| Hybrid input | Touch plus mouse or stylus | Touch targets stay large while hover becomes available |
| Keyboard device | Touch plus attached hardware keyboard | Tab/arrow traversal, Enter/Space activation, no forced software IME |
| Accessibility device | Font scales 1.0, 1.3, 1.5 and 2.0; TalkBack on | Text clipping, semantic order, spoken labels |
| Minimum runtime | Android 8/API 26 with legacy insets | Stable/IME separation and lifecycle compatibility |
| Current runtime | Android 15+ with enforced edge-to-edge | Cutout, gesture and IME inset delivery |

If hardware cannot provide a fold or cutout posture, an emulator may exercise
geometry and IME behavior, but it does not replace at least one physical ARM64
touch run for input latency, haptics, thermal behavior or GPU results.

## Journey matrix

Run every journey in both orientations on the compact and cutout classes, and
once on every other applicable class.

| Journey | Actions | Pass criteria |
| --- | --- | --- |
| World navigation | Move, look, change view, open/close action bar controls | No stuck capture; bars do not overlap protected edges; touch response is immediate |
| Tablet navigation | Open Tablet, change launcher page, enter/leave each enabled app, use Back, close | Back order is modal → app → home → world; no world input leaks through Tablet |
| Address | Open Go To, enter/edit a long address, show/hide IME, submit and cancel | Focused field remains visible; no duplicate submit; secret/private text absent from diagnostics |
| Login | Traverse username/password/actions by touch and keyboard; fail once, retry, cancel | Password stays masked; focus moves predictably; IME never covers the active field; teardown clears the password |
| Settings | Scroll all categories, change boolean/slider/number/combo values, Save/Cancel | A drag does not activate rows; every control has a target of at least 48 rendered px; values persist/revert correctly |
| Avatar | Open settings, edit both URL fields, change scale, Save/Cancel | Long text and 1.5× UI text do not clip actions; focused URL remains above IME |
| Audio | Scroll, toggle microphone/audio controls, change sliders and devices | Labels remain legible; controls are reachable; meter/listener teardown is clean |
| Security | Toggle protection, edit multiline allowlists, use help and Save | URL keyboard hints appear; text scrolls; all actions are reachable with TalkBack and keyboard |
| Emote | Scroll and activate first/last item at narrow/medium/expanded widths | Grid uses 2–4 columns; drag never fires an emote; selected state is announced |
| Web text entry | Focus and blur a web field, navigate away while IME is visible | Exactly one system keyboard appears; legacy HMD keyboard remains hidden; no residual inset |
| Dynamic change | Rotate, resize, attach/detach mouse and keyboard with Tablet/form open | Layout updates once without crash, restart, stale safe area or lost actionable focus |

## Accessibility gates

- Every interactive element has one meaningful accessible name, role and
  description/state; decorative `MouseArea` objects are ignored.
- TalkBack traversal follows visual reading order and reaches Back, page,
  Save/Cancel and close actions exactly once.
- Enter and Space activate focused buttons/menu rows; Tab reaches every form
  action; arrows keep their established list/page behavior.
- At system font scale 1.5, no label required to operate the UI is clipped or
  overlaps another action. At 2.0, the app remains operable because the shared
  UI intentionally caps internal layout scale at 1.5.
- Touch exploration and a connected pointer do not shrink the rendered 48 px
  minimum target or create hover-only actions.

## Geometry and IME gates

- No actionable pixel is placed inside a reported display cutout, mandatory
  gesture inset or visible IME inset.
- Left, top, right and bottom protection are verified independently; a larger
  left cutout must not introduce an equal right margin.
- Showing the IME does not change the content scale. The current field scrolls
  into view with one stable movement and remains visible while validation text
  appears.
- Hiding the IME, rotating or leaving a form removes its transient bottom inset
  and never leaves a blank keyboard-sized region.
- During fold/multi-window transitions, a transient zero or over-inset surface
  is ignored and the last usable layout remains intact until a valid snapshot
  arrives.

These gates follow Android's current
[edge-to-edge recommendations](https://developer.android.com/develop/ui/views/layout/edge-to-edge),
[`WindowInsets` API](https://developer.android.com/reference/android/view/WindowInsets.html)
and [IME visibility guidance](https://developer.android.com/develop/ui/views/touch-and-input/keyboard-input/visibility).

## Performance gates

Use a 120-second run after a 30-second warm-up in the same quiet scene for the
baseline and candidate. Capture at least three runs per device class and use
the median report.

- Process remains stable; crash count does not increase; thermal status stays
  below severe throttling.
- Native present rate stays within 10% of the configured 30 FPS target.
- Candidate p95 frame time and janky-frame percentage regress by no more than
  10% relative to that device's accepted baseline.
- Opening/closing Tablet 50 times and showing/hiding the IME 50 times produces
  no monotonic growth across three consecutive memory samples after returning
  to the same idle scene.
- A 100,000-snapshot host normalization pass remains below five seconds; this
  generous CI ceiling detects accidental super-linear work in a
  layout-adjacent callback, not real device input latency.

Do not compare raw frame or memory values across unrelated hardware. Store an
accepted baseline per anonymized device class and build mode. A regression is
resolved by investigation or an explicitly reviewed baseline update, never by
silently deleting a row.

## Result record

For each row, retain: revision, APK SHA-256, debug/release mode, Android API,
device class, posture/navigation/input/font configuration, journeys completed,
benchmark summary path, pass/fail and a short sanitized note. Mark unexecuted
rows `not run`; do not infer a physical pass from the host suite.
