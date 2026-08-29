# Pico 4 controller automation decision

This document covers physical-device E2E input for Overte on a PICO 4. Input is
disabled by default. The Android Pico adapter exposes the six semantic operations
only behind the explicit Debug-E2E lab opt-in described below; CI and unqualified
labs continue to omit them until the hardware gates are complete.

There are two deliberately separate input domains behind the shared layer and
host transport. `input.look` offsets the HMD/head VIEW pose and never injects a
controller action. Movement, tablet toggling, buttons, sticks, triggers, grips,
and controller poses use the controller action/space path.

## Decision

Use a test-only, app-packaged **explicit OpenXR API layer** as the controller
driver. Keep ADB as an authenticated transport to app-private command files,
not as the controller protocol. This reaches the same `xrGetActionState*` and
`xrLocateSpace` calls that Overtes Pico input plugin already consumes, supports
every required channel, and can be removed mechanically from release APKs.

Do not use Android key injection, UHID, AOA, scrcpy gamepad mode, or a PICO SDK
hook as the primary XR controller backend. Those mechanisms create Android
framework key/gamepad events. Overtes immersive Pico input path reads OpenXR
actions directly, and the PICO runtime has no documented mapping from an
arbitrary Android gamepad to the ByteDance PICO 4 OpenXR interaction profile.
They also cannot supply a tracked controller pose.

## Capability matrix

| Requested channel | ADB `input` | Android HID/UHID or scrcpy | PICO public APIs | Test-only OpenXR layer |
| --- | --- | --- | --- | --- |
| A/B/X/Y and stick click | Android key event only | Android gamepad event | read controller state | **Yes**, boolean action |
| Menu | Android key event only; OS interception | Android gamepad event; OS interception | read state | **Yes**, but use Y for the user-realistic tablet path |
| Thumbstick X/Y | no durable analog hold on Android 10 shell | Android joystick axes | read state | **Yes**, vector2f action |
| Trigger | key-like at best | gamepad axis/button | read state | **Yes**, float plus click action |
| Grip | key-like at best | gamepad axis/button | read state | **Yes**, squeeze float action |
| Controller position/orientation | No | No | read/offset APIs, no input simulator | **Yes**, pose action space plus `xrLocateSpace` |
| Head look | No OpenXR pose | No OpenXR pose | read pose | **Yes**, view/reference-space composition |
| Works without paired controllers | not an XR input | not an XR input | No documented simulator | **Yes**, for the E2E debug APK only |
| Release isolation | external | external | vendor dependency | **Yes**, package-exclusion gate |

PICO's own documentation describes controller state retrieval and a desktop
PICO Emulator. It does not document a real-device API for setting controller
button, axis, or tracking state. The emulator is useful for developer feedback,
but it is not a physical-device gate and is not the open-source Fedora-side
foundation required by this lab.

## Exact Overte action bindings

[`pico4-overte-controller.json`](profiles/pico4-overte-controller.json) is an
allowlist copied from Overtes `OpenXrInputPlugin.cpp`, not a generic OpenXR call
surface. It covers:

- left X/Y/Menu, right A/B, trigger click, and both stick clicks as booleans;
- both thumbsticks as `XrActionStateVector2f`;
- both trigger and squeeze/grip values as `XrActionStateFloat`;
- both grip poses through their action spaces.

The system button is deliberately absent. The real PICO runtime may reserve it,
and a test must not synthesize operating-system controls. The real left Menu
button is also commonly intercepted by PICO OS. A semantic tablet test should
therefore inject Overtes tested Y-button fallback. A separate low-level binding
test may exercise `menu_click` inside the app layer, but must not claim that the
physical Menu button reaches the app.

## Native interception boundary

The layer must call the next layer/runtime first and only overlay action handles
recorded from exact `xrCreateAction` names and types. The minimum interception
set is:

- `xrCreateAction`, `xrSyncActions` and the boolean/float/vector2f action-state
  getters for buttons and axes;
- `xrCreateReferenceSpace`, `xrCreateActionSpace`, `xrGetActionStatePose`, and
  `xrLocateSpace` for controller poses;
- `xrLocateViews` plus VIEW-reference-space composition for HMD/head look; this
  path never modifies a controller action.

Overte locates its controller action spaces relative to STAGE space. The first
native version should reject any synthetic pose query with a different base
space instead of guessing a coordinate transform. Unknown actions and calls
always delegate unchanged. Published state changes only on `xrSyncActions`, and
each command ends in a neutral snapshot. A watchdog neutralizes every channel
if the host disappears.

Android activation requires an E2E-only build variant that packages the layer
manifest in APK assets below `openxr/1/api_layers/explicit.d` and the native
library for `arm64-v8a`. The same variant must explicitly add the layer name to
`XrInstanceCreateInfo.enabledApiLayerNames`. Release builds must package neither
artifact and must contain no activation marker.

For vertical locomotion, the Pico binding maps a bounded
`right_secondary_click` pulse or hold through `OpenXR.RightSecondary`,
`Standard.RightSecondaryThumb`, and `Actions.Up`. The debug-only launcher makes
right-hand dominance, advanced movement, and flying effective only for that
process; it never writes the user's stored movement or flying preference.

The existing short-lived session grant and app-private atomic ADB transport in
this directory remain the activation boundary. The new controller envelope adds
no path, shell, script, arbitrary action name, or raw OpenXR function field.

## Hardware gates before capability advertisement

The shared `overte_e2e_probe.js` now exposes read-only `Controller.Standard`
button/axis values and left/right `getPoseValue()` output. Invalid poses carry a
false validity bit and null transforms. This observation path is independent of
the API-layer acknowledgement in the app-private `status.json` transport.

1. Verify the E2E debug APK reports the exact build marker, layer name, profile
   hash, accepted nonce, and sequence through app-private `status.json`, then
   verify injected values independently through the controller probe.
2. Inspect the APK and prove the layer manifest, binary, marker, and test
   transport are absent from release output.
3. For every channel, inject one bounded pulse/hold and observe the corresponding
   Overte controller probe value. An acknowledgement from the layer is not
   sufficient.
4. Verify Y opens/closes the tablet, the left stick moves the avatar, a short
   right-secondary pulse jumps, a bounded right-secondary hold flies upward,
   trigger drives laser selection, grip drives grab state, and a known grip-pose
   delta moves the rendered/controller probe by the expected amount.
   The debug probe must first attest right-hand dominance and advanced movement
   controls; otherwise Overtes preference-dependent mapping may consume the
   left locomotion stick as a basic-movement turn command.
5. Disconnect or sleep the host during every action type and prove the watchdog
   returns buttons, floats, vectors, and poses to neutral/inactive.
6. Verify replay, stale nonce, malformed command, wrong profile hash, wrong base
   space, controller disconnect, OpenXR session loss, and app restart all fail
   closed.
7. Compare a physical controller sample with a synthetic sample to confirm Pico
   signs, handedness, thresholds, pose axes, and button edge timing.

## Preliminary physical Pico 4 inventory (2026-08-25)

A read-only inspection of the attached A8110, selected by its private target
file on an isolated ADB server, confirmed Android 10/API 29 and the installed
`com.pico.xr.openxr_runtime` package. The device exposes `input`, `getevent`, and
`sendevent`, but no `hid` or `uinput` command. `/dev/uhid` and `/dev/uinput` are
writable by the authorized shell account, so a host tool could create an Android
HID/gamepad if one were ever needed for non-XR UI coverage.

Android InputReader did not expose the physical PICO controllers as joystick
devices. Its five `pvr-virtual-input-*` devices provide display-oriented touch,
key, and pointer capabilities, but no thumbstick, trigger, grip, or tracking
pose axes. The remaining `virtual_input_device` exposes only pointer-like
`ABS_X`/`ABS_Y`. This device evidence matches the architectural boundary:
Android injection is not the PICO OpenXR controller transport.

One bounded `input gamepad keyevent KEYCODE_BUTTON_A` completed successfully
while Overte was stopped. It did not start Overte or change the focused/resumed
PICO window, and no matching controller/OpenXR log entry appeared. This is not
yet an in-app negative gate; repeat it while the E2E APK and controller probe
are active. It does prove that command success alone is not controller evidence.

Use the privately pinned `$ANDROID_SDK_ROOT/platform-tools/adb -P <isolated-port>
...` form or the standard `ANDROID_ADB_SERVER_PORT=<isolated-port>` environment
variable for this lab. The similarly named `ADB_SERVER_PORT` is ignored by the
validated Platform Tools and must not be used in isolation checks. Port numbers
and device selectors remain private lab configuration.

## Device-free prototype

`controller_protocol.py` validates the exact target binding, compiles bounded
physical-control commands into sync-boundary snapshots, and models query
stability and watchdog cleanup. It performs no ADB operation and cannot enable
an API layer:

```bash
python3 -m unittest tests.device.self_tests.test_openxr_controller_protocol -v
```

`adapter_session.py` connects the bounded transport to the universal Pico
adapter without changing the common modules. Because each adapter invocation is
a new host process, it stores only a hashed target key, process identity,
private nonce, and next sequence in a mode-`0700` runtime directory with
mode-`0600` state. A target-process restart fails the run closed instead of
rotating into a new session. The adapter waits for native identity/sequence
acknowledgement, confirms a neutral window between commands, and confirms
neutral cleanup before it stops Overte. The selector and nonce never enter
operation results or test artifacts.

The lab opt-in requires `OVERTE_ANDROID_E2E_DEBUG=1`,
`OVERTE_PICO_OPENXR_INPUT=1`, a non-default Pico-only
`ANDROID_ADB_SERVER_PORT`, and a private explicit state directory or
`XDG_RUNTIME_DIR`. A present but incomplete opt-in fails configuration instead
of silently falling back to a weaker input path.

The Debug-only native implementation lives under
`android/vr/pico/apps/picoInterface/openxr/e2e_input`. Its production build
path is mechanically absent unless Gradle enables
`OVERTE_PICO_E2E_OPENXR_INPUT`; the release variant explicitly disables it.
`android_transport.py` writes the validated command envelope first and the
short-lived grant as the atomic commit marker. It requires an isolated ADB
server with exactly the private Pico selector and never places the selector,
nonce, or JSON payload into reports.

## Primary sources

- [OpenXR 1.1 specification](https://registry.khronos.org/OpenXR/specs/1.1-khr/html/xrspec.html),
  especially API layers, actions, spaces, and the ByteDance PICO 4 controller
  interaction profile.
- [Khronos OpenXR loader API-layer design](https://github.com/KhronosGroup/OpenXR-SDK-Source/blob/main/specification/loader/api_layer.adoc),
  including Android APK asset discovery.
- [Khronos open-source API-layer implementations](https://github.com/KhronosGroup/OpenXR-SDK-Source/tree/main/src/api_layers),
  Apache-2.0/MIT scaffolding for the native implementation.
- [Android 10 `input` shell source](https://android.googlesource.com/platform/frameworks/base/+/android10-release/cmds/input/src/com/android/commands/input/Input.java),
  which constructs Android `KeyEvent` and `MotionEvent` objects.
- [AOSP HID command documentation](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/cmds/hid/README.md),
  which documents creation of a Linux/Android joystick device.
- [scrcpy open-source gamepad documentation](https://github.com/Genymobile/scrcpy/blob/master/doc/gamepad.md),
  which documents UHID/AOA physical-gamepad simulation.
- [PICO controller and HMD input mapping](https://developer.picoxr.com/document/unity-openxr/input-mapping/),
  which documents controller state paths but no physical-device input setter.
- [PICO Emulator UI](https://developer.picoxr.com/document/spatial-toolkit/pico-emulator-ui/),
  a developer emulator rather than a physical-device controller injection API.
