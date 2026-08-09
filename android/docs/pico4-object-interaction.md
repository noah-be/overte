# Pico 4 object interaction

This document describes the Pico 4 controller-to-entity interaction path, the
current implementation status, and a repeatable hardware test procedure.

## Signal path

```text
Pico 4 controller
  -> Pico OpenXR runtime (XR_BD_controller_interaction)
  -> android/apps/picoInterface/openxr/OpenXrInputPlugin
  -> OpenXR hardware channels
  -> interface/resources/controllers/openxr.json
  -> Controller.Standard hand, trigger and grip channels
  -> scripts/system/controllers/controllerDispatcher.js
  -> near/far grab, trigger, web-surface and HUD pointer modules
  -> Picks / Pointers / MyAvatar.grab / entity script methods
```

The Pico client uses the normal Overte controller interaction scripts. There
is no separate Pico grab implementation. Pico-specific correctness therefore
depends on the Android OpenXR plugin supplying the same standard inputs as the
desktop OpenXR plugin expects.

The Pico OpenXR device clears pose, button, and axis state at the start of each
input update. An inactive action after tracking loss therefore reads as neutral
instead of retaining the previous trigger, grip, or stick value. The device-
free ordering contract is `python3 android/tests/pico-openxr-input-test.py`.
If `xrSyncActions` fails, the update returns with those neutral maps instead of
querying and republishing potentially stale action state.
Its tracked-controller count also starts at zero each update and increases only
for controller locations with valid orientation, so availability no longer
remains hard-coded to two during session or tracking loss.
Individual OpenXR action getters likewise return neutral state on query errors.
Pose spaces are located only while their action is active, and failed locations
cannot contribute a valid controller pose.

If a dispatcher module is disabled while running, its occupied activity slots
are released by checking ownership on the slot table itself. This prevents a
removed grab, Web, HUD, keyboard, or Create module from permanently blocking
the next module that needs the same Pico hand or trigger slot.

Off-hand far-grab rotation now reads the other controller's quaternion only
when that pose is currently valid. Losing tracking on the manipulating hand
preserves the last valid rotation and exits manipulation without interrupting
translation from the hand that still owns the grab.

## Static implementation audit

The Android OpenXR plugin enables `XR_BD_controller_interaction` when the
runtime advertises it and installs the Pico 4 interaction profile. It maps:

- controller grip poses to `Standard.LeftHand` and `Standard.RightHand`;
- analog triggers to `Standard.LT` and `Standard.RT`;
- trigger clicks (including Overte's 0.95 virtual click) to `LTClick` and
  `RTClick`;
- analog squeeze inputs to `Standard.LeftGrip` and `Standard.RightGrip`;
- thumbsticks, face buttons, touch state, Menu, and haptics.

The controller dispatcher consumes those channels as follows:

- trigger value makes an entity eligible and displays/updates a ray;
- trigger click starts near/far grabbing or activates a pointer target;
- squeeze/grip can start and retain a near grab;
- the hand pose provides the near-search position and the far ray direction;
- grab modules call `MyAvatar.grab()` or create a far-grab action and send
  `Hifi-Object-Manipulation` plus entity-script callbacks.

The Khronos Pico 4 profile also exposes an `aim/pose`. Overte currently uses
the `grip/pose`, applies generic Touch-style pose offsets, and derives the ray
from that transformed hand pose. Hardware testing must establish whether this
causes a systematic Pico ray or grab-point offset before changing pose math.

## Diagnostic script

Run `scripts/developer/debugging/pico4ObjectInteraction.js` from the Running
Scripts window. In Logcat, filter for `PICO4_INTERACTION`.

The script records:

- validity and position of both `Controller.Standard` hand poses;
- analog trigger, trigger-click, and grip values;
- the entity intersected by the same grip-derived ray used by the dispatcher;
- local `Hifi-Object-Manipulation` grab/release events;
- analog trigger, trigger-click, grip, target, tracking-validity, and invalid-
  pose counters when the script stops.

Input transitions are sampled on `Script.update`, while the full state summary
remains throttled to once per second. This allows short trigger-click or
tracking-loss sequences to be counted without flooding the log each frame. The
mocked device-free regression is
`node android/tests/pico-interaction-diagnostics-test.js`.

The script is diagnostic only. It does not create or modify test entities and
does not replace the normal controller dispatcher.

For dispatcher, laser, Near Grab and Far Grab edge records, explicitly load
`scripts/developer/debugging/pico4InteractionTraceControl.js`. Stop that script
after the capture. It is never loaded by the fixture station and normal Pico
sessions therefore do not pay its logging cost. Earlier high-rate diagnostic
captures measurably reduced whole-client responsiveness; timings captured with
verbose diagnostics must not be treated as production latency.

## Hardware test matrix

The Pico development client starts in the bundled, spawn-aligned test world
`file:///~/serverless/overte-hub-pico4-optimized-spawn.json`. For an ordinary
launch, the Pico startup path initializes the avatar once at `(0, 1, 0)` before
navigating to this URL; neither the world nor a later test script is moved. The
position is deliberately not encoded as a URL `location` query, because later
serverless address handoffs can replay such a viewpoint and teleport a moving
avatar back to spawn. This intentionally
overrides a remembered previous location for ordinary Pico launches, while an
explicit command-line `--url` remains available for targeted tests.
The Pico loading overlay detects serverless mode before checking domain
connectivity: local JSON loading proceeds directly to the world-data and
resource phases and never displays or waits on a domain-server handshake. Once
loading has advanced beyond `CONNECTING`, both immediate and debounced phase
updates are prevented from regressing to it.
Octree resets use the same rule: a serverless reset preserves
`RECEIVING_WORLD` as the initial native-overlay phase instead of directly
forcing `CONNECTING` outside the normal phase state machine.
After the local JSON import populates the live entity tree and the serverless
connection signal performs its synchronous Octree reset, the loader confirms
serverless mode again. This clears the reset handoff guard before the full-scene
counter advances, allowing physics and the playable-frame handoff.
Delayed disconnect notifications from an earlier online entity server are
ignored while the active world is serverless. They otherwise repeatedly clear
the freshly imported local Octree before physics can be enabled.
The same protection applies to redundant domain-reset signals after a local
full scene has been committed. This state is tracked independently from the
full-scene counter because a reset clears that counter immediately. Re-emitting
the same serverless URL preserves the import; a genuinely different URL clears
it normally. The initial reset before import is still allowed.
Physics startup uses the same serverless test as the loading UI: either the live
entity tree or the domain handler's active `file:` URL. If the URL has advanced
before the tree mode, the update loop repairs the tree state and begins the
normal GPU/avatar physics-readiness checks instead of remaining at 25%.
On Pico, bundled local JSON worlds are resolved through `PathUtils` and read
directly before physics readiness is evaluated. This avoids an asynchronous
local-resource callback being starved by an early physics-finalization check.
While that initial local import is pending, Pico does not enter the online
Safe-Landing path; doing so can block startup before address navigation runs.
As a Pico lifecycle fallback, the first update with an available live EntityTree
directly imports the bundled startup world exactly once if normal address
navigation has not committed it yet.
For a committed local serverless scene, Pico starts physics from the imported
entity/collision tree without waiting for Android texture streaming to become
idle. Visual resources continue in the background, while the presented-frame
handoff keeps the overlay visible until a scene frame is available. Online
worlds retain the stricter idle-queue and GPU-stability gate.
If later graphics initialization reloads resource caches, physics/GPU readiness
is reset but a committed serverless mode and full-scene milestone are restored;
the cache reload must not invalidate the already imported entity scene.
Loading-screen packet recovery is disabled for serverless worlds because they
have no entity-server sequence to retry. Restarting Safe Landing there clears
the synthetic full-scene milestone and traps the UI at 25%.
The bounded Serverless GPU handoff therefore trusts the successful local JSON
import itself, not the network full-scene counter. That counter is meaningful
only for entity-server packet streams and may be reset independently of the
already populated local tree.
Serverless GPU and avatar-readiness timeouts use the stable world-measurement
start rather than resettable finalization milestones, so later cache or
Safe-Landing resets cannot postpone the playable handoff indefinitely.
Serverless startup uses safe default avatar scale limits because no domain
settings server exists. A committed and physics-active local scene also ignores
delayed teardown/reset notifications from the previously remembered online
domain.
Every ordinary Pico launch performs a real address lookup for the bundled test
world. Loading it only as remembered address settings updates the displayed URL
but does not emit `domainURLChanged()` and therefore never imports the JSON.
The startup URL may be reported once with the `~/serverless` alias and later as
its expanded Android cache path. Both forms are normalized before comparison;
otherwise the same world is mistaken for a competing domain every few seconds,
physics is reset before the render handoff completes, and the overlay remains
at 25%. Until the bundled scene reaches READY, genuinely competing remembered
domain URLs are ignored. Later explicit navigation remains available.
The legacy interstitial script must not query its loading sphere as an entity.
It reconstructs the known avatar-relative transform instead. Treating that
overlay ID as an entity yields an undefined orientation on Pico, crashes
`Quat.inverse()`, and leaves a large head-relative white surface with a red
outline in front of the loaded world.
Pico exposes `Window.nativeLoadingScreenEnabled`, so its default scripts do not
start the legacy JavaScript interstitial at all. This prevents the legacy
overlay from blinking when transient domain state changes after the native
loading screen has already released the scene. Other clients retain their
existing interstitial behavior.

Before every timed interaction capture, fix the Pico fan at 100% and verify the
reported duty. This keeps thermal throttling from being confused with input or
pick latency:

```bash
adb -s <pico-address>:5555 shell gd32ipdclient_test setfantestmode 1
adb -s <pico-address>:5555 shell gd32ipdclient_test setfantestspeed 100
adb -s <pico-address>:5555 shell gd32ipdclient_test getfanspeed
adb -s <pico-address>:5555 shell dumpsys thermalservice
```

`getfanspeed` must report `100`, and the thermal status and temperatures must
be captured with the interaction log. Restore automatic fan control after the
test session with `gd32ipdclient_test setfantestmode 0`.

Use one small dynamic entity with `grabbableKey.grabbable: true`, one large or
distant grabbable entity, and one entity with a script that logs
`startNearGrab`, `continueNearGrab`, `startDistanceGrab`, and `releaseGrab`.
The bundled optimized Hub snapshots contain no dynamic or explicitly grabbable
entities, so merely pointing at Hub scenery is not a valid grab test. Run
`scripts/developer/debugging/pico4InteractionTestStation.js` to place a red
near-grab cube, a blue far-grab cube, and a yellow non-grabbable control cube
in front of the avatar. The fixtures are local, expire after one hour, and are
removed when the script stops. The station does not start any diagnostic
script. It removes the global
`DebugWorkloadSelection` and
`Hovering` developer-render selections at startup, because their
mouse/gaze-directed pale-red outlines would invalidate the visual test.
Controller grab highlighting is intentionally left unchanged.
When the optional trace controller is running, grab and laser transition
records can be correlated in Logcat without enabling the former continuous
fixture sampling.

Serverless imports and the interaction fixtures use `local` entities. A simple,
unparented local Far Grab is parented directly to the actual avatar controller
joint after a fail-closed eligibility check. This avoids the delayed local
physics-action presentation path while preserving the initial world transform
and restoring the previous parent on release. Domain and avatar entities retain
the standard `MyAvatar.grab()` and entity-script paths.

While either hand holds a far-grab, the Pico right thumbstick adjusts target
depth: forward moves the object farther away and backward brings it closer.
The input uses a `0.2` deadzone, scales speed with the current distance, and is
clamped to a `0.25`–`20 m` range. A separate 60 Hz script engine performs this
local-only update through `Entities.setLocalEntityPosition()`, which rejects
domain/avatar entities and invalid coordinates and avoids edit packets,
ownership bids and octree traversal. The existing lateral controller motion and
off-hand rotation behavior remain available. Pico disables the legacy radial
hand-velocity depth adjustment because small controller motion while squeezing
the trigger was amplified and pulled a newly selected object toward the hand.
The acquired distance now remains fixed until the right thumbstick changes it.
While the left controller owns a far grab, Pico also temporarily suppresses
the teleport module. Otherwise the right-stick depth input simultaneously
displayed the teleport target and could lead to an unintended teleport. The
normal teleport behavior becomes available again as soon as the grab ends.

Overte's application HUD normally draws a red full-surface border whenever the
domain handler is disconnected. A serverless scene intentionally has no domain
connection, so this produced a permanent red head-relative rectangle despite a
successfully loaded world. The border now treats both application and domain-
handler serverless modes as valid; genuine failed online connections still show
the warning.
The Pico client starts the lightweight fixture station on every launch after
the local acceptance scene is committed and physics is enabled. The fixtures
are placed relative to the serverless avatar spawn. This does not enable edge,
dispatcher, controller-sampling, or other interaction diagnostics; those
remain explicit developer actions.

Pico interaction thresholds are centralized under `pico/interaction/*` and are
available on the Pico-only Settings page. Invalid or non-monotonic trigger
threshold combinations fall back to the tested defaults: release `0.05`, white
laser `0.10`, green selection `0.50`, and purple Far Grab `0.90`; Grip uses
release `0.10` and grab `0.50`. The independent world-laser worker reads the
same shared values, so a fast full press does not remain green while entity
lookup and grab initialization complete.

1. Point each controller at the same visible landmark. Confirm the logged
   target changes where the rendered ray crosses the landmark.
2. Slowly press each trigger. Confirm an analog ramp from 0 to 1 and exactly
   one click transition near full press, followed by a release transition.
3. Slowly press each grip. Confirm an analog ramp and that a near object can be
   grabbed, retained, and released without trigger input.
4. Near-grab the small object with trigger, then with grip. Check position,
   rotation, haptic feedback, callbacks, and one grab/release message pair.
5. Far-grab the distant object with each hand. Move it laterally and in depth,
   rotate it with the off hand, then release it.
6. Click a Web entity, tablet/HUD control, and entity with `wantsTrigger`.
   Confirm hover, press, drag, release, and scrolling.
7. Repeat after briefly losing controller tracking. A pose may become invalid,
   but an active grab must end safely and interaction must recover.

Capture the headset firmware version, dominant hand, test entity IDs, Logcat
output, and whether the visible ray agrees with the physical pointing axis.
For an aim-offset defect, record whether the angular error is stable for each
hand; this distinguishes a pose transform error from tracking latency.

When several Android worktrees share the Conan cache, `build-pico.sh` resolves
Draco from the Pico ARMv8 generator metadata rather than selecting the newest
Draco cache entry. This prevents a concurrent host or phone build from staging
an x86-64 archive into the Pico compatibility directory.

## Open hardware tests

Basic direct grab and far grab, including right-thumbstick depth control, have
been confirmed on Pico 4. The following regression and edge-case tests remain:

Pico controller rays are disabled while idle to reduce their continuous pick
cost. Trigger input now wakes the corresponding world and HUD rays directly
from the input mapping, before the frame's pick update. This prevents the first
far-grab click from using an idle or stale ray result, which could make distant
objects (for example at roughly 2 m) impossible to select while nearby direct
grabs still worked.

Pico's OpenXR analog trigger was observed reaching approximately `0.905` while
its digital `RTClick` route remained zero. Because far grab requires a logical
click after acquiring the ray target, the Pico dispatcher synthesizes that
click at an analog value of `0.90` and releases it below `0.10`. The hysteresis
prevents chatter, and a real digital click still takes precedence when present.
The corresponding world search beam activates at `0.50`, including while the
ray has no current entity intersection. This provides a deliberate half-press
aiming stage before the near-full-press selection and grab stage.
Pico diagnostics emit throttled `PICO4_RAY_SEARCH` records while a trigger is
held, separating world and HUD intersections so a fixed HUD-surface beam cannot
be mistaken for a dynamic entity hit.

Pico does not honor the `combineHudAndWorldPointers` setting. A combined pointer
reported the HUD intersection at approximately `1.13 m` as both its world and
HUD result, so the visible beam stayed at tablet distance and never reached a
more distant entity. Dedicated world rays exclude `Picks.PICK_HUD`; dedicated
HUD rays continue to handle the tablet and other 2D surfaces.

- [x] Test direct grab and far grab independently with both hands. Both paths
  have been confirmed with the left and right Pico controllers.
- [x] While the left hand holds a far grab, verify that the right thumbstick
  still controls depth. Confirmed on Pico 4.
- [x] Release a grabbed object during a fast controller movement. The object
  released correctly with plausible physics and did not snap back, remain
  attached, or become unstable.
- [x] Pull an object from far-grab range into near-grab range, release it, and
  immediately grab it directly. The Pico test completed without a stuck ray,
  target, grab state, or position snap during the handoff.
- [x] Try direct and far grab on the yellow non-grabbable control cube. Both
  interaction paths correctly left the control cube immovable on Pico 4.
- [x] Verify right-thumbstick depth edge cases: no drift inside the deadzone,
  controlled motion in both directions, a safe `0.25 m` minimum, and a usable
  `20 m` maximum. All limits, release behavior, and deadzone stability were
  confirmed on Pico 4.
- [x] While changing the depth of a left-hand far grab with the right
  thumbstick, no teleport target or play-area UI appeared, and normal teleport
  behavior became available again after releasing the object.
- [ ] Verify off-hand rotation during far grab. Pico inherits the desktop
  mapping: pressing the other hand's trigger or secondary input applies that
  controller's rotation delta. No Pico-specific threshold or rotation math was
  added, and this behavior has not yet been confirmed on the headset.
- [ ] Rapid trigger/grip and tracking-interruption stress testing is deferred
  until the known interaction performance problem is resolved; current frame
  delays make its timing and results unreliable.
- [ ] Web-entity interaction is implemented and tracked separately in
  `android/docs/pico4-web-entities.md`. Keep the controller acceptance results
  there independent from the already confirmed object-grab behavior.

## Deferred performance investigation

Grabbed object motion is generally slow and trails slightly behind the visible
controller laser. This was observed across multiple interaction paths rather
than only during far grab, so it does not invalidate the successful fast-release
and physics test above. The Pico fan was fixed at `100%` during testing, making
thermal throttling an unlikely explanation for that session. Profile the shared
entity update, physics, pointer, and grab propagation paths separately before
changing interaction behavior.

## Acceptance criteria

- Both hand poses remain valid while controllers are tracked.
- Trigger and grip inputs cover their analog range and release to zero.
- Both thumbstick axes return near zero when released; an absolute Y value over
  `0.65` continuously activates Overte's teleport target and play-area overlay.
- Near and far interaction work symmetrically for both hands.
- One physical press produces one logical press/release sequence.
- The rendered ray and selected entity agree with the user's pointing intent.
- Object motion follows the controller without a persistent offset or visible
  extra-frame lag.
- Losing tracking or switching targets leaves no stuck grab or stuck click.

## Source references

- `android/apps/picoInterface/openxr/src/OpenXrContext.cpp`
- `android/apps/picoInterface/openxr/src/OpenXrInputPlugin.cpp`
- `interface/resources/controllers/openxr.json`
- `scripts/system/libraries/controllers.js`
- `scripts/system/controllers/controllerDispatcher.js`
- `scripts/system/controllers/controllerModules/nearGrabEntity.js`
- `scripts/system/controllers/controllerModules/farGrabEntity.js`
- `scripts/system/controllers/controllerModules/nearTrigger.js`
- `scripts/system/controllers/controllerModules/webSurfaceLaserInput.js`
