# Android Phone device adapter

This target adapter maps the universal harness operations to ADB for the
regular `org.overte.phone` client. Discovery accepts only authorized physical
ARM64 touchscreen phones with Android API 26+, OpenGL ES 3.0+, and rejects
emulators, watches, TVs, automotive, VR, Pico, and ByteDance targets.

Run the portable smoke suite against the only connected eligible phone:

```bash
python3 tests/device/run.py \
  --adapter-manifest android/phone/device-tests/adapter.json \
  --catalog tests/device/catalog.json \
  --suite smoke
```

Stability duration and cycle controls are shared across platforms:

```bash
OVERTE_DEVICE_LIFECYCLE_CYCLES=20 \
OVERTE_DEVICE_IDLE_SECONDS=1800 \
python3 tests/device/run.py \
  --adapter-manifest android/phone/device-tests/adapter.json \
  --catalog tests/device/catalog.json \
  --suite stability --output-dir /tmp/overte-phone-stability
```

The Phone APK must already be installed. Installation and APK provenance remain
an explicit preparation gate rather than a hidden side effect of every module.

## Debug fixture and probe

An E2E-enabled debug APK exposes `scene.load` and `probe.snapshot` only with
the shared debug opt-in:

```bash
OVERTE_ANDROID_E2E_DEBUG=1
```

`scene.load` accepts exactly the embedded
`overte-e2e://fixture/scene` URL. It starts the shell-only Phone E2E launcher,
waits for two fresh samples containing all four fixture markers, and then
applies the repository-owned spawn viewpoint through the exported
`PermissionsActivity` deep-link flow. `PhoneInterfaceActivity` and the native
URL handler therefore reach the normal AddressManager path; the adapter never
writes the avatar position.

The launcher records its process identity in a private, selector-hashed host
session. `probe.snapshot` requires that binding before and after reading the
app-private debug artifact with `run-as`. This avoids repeating full device
profile discovery during every poll, so a bounded non-flying jump remains
observable. Stale snapshots and changed processes fail closed. Cleanup stops
the package and removes the host session without modifying Android settings or
saved Overte preferences.

## Vertical locomotion input

The adapter advertises `input.jump` and `input.fly` only when the dedicated
Android Phone lab explicitly sets:

```bash
OVERTE_ANDROID_PHONE_E2E_INPUT=1
```

This opt-in does not apply to Pico, VR, emulators, or non-phone Android
profiles. Before every locomotion action the adapter requires the expected
package to be installed, running in the foreground, and bound to one unchanged
process identity.

Both operations inject a real touch into the production landscape virtual-pad
jump button. The normal Phone mapping then carries the input through
`TouchscreenVirtualPad.JUMP_BUTTON_PRESS`, `Actions.VERTICAL_UP`, and
`MyAvatar::TRANSLATE_Y` to the character controller. `input.jump` emits one
120 ms press. `input.fly` holds the same action for its requested finite
`durationSeconds` from `0.1` through `10.0`. Android's bounded swipe supplies
its normal release, and the adapter also injects a fail-closed `ACTION_UP` in a
`finally` path and during cleanup.

No avatar state or position is written directly. The adapter does not change
or persist flying preferences or any other user setting.
