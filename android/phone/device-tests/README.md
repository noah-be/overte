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
which supplies the shared fixture URL and viewpoint through Android's normal
startup arguments. After binding the process, the adapter uses a DUMP-protected
debug Activity to request a process-only flying override of `false`, waits for
the fixture and grounded avatar, then requests `true` for the flight test. The
adapter requires fresh shared-probe samples for every transition. No second
navigation, address field, software keyboard, direct avatar write, or stored
preference change is used.

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
`MyAvatar::TRANSLATE_Y` to the character controller. `input.jump` emits exactly
one `ACTION_DOWN`, one stationary `ACTION_MOVE`, holds for 120 ms, and emits
`ACTION_UP`. The update mirrors the natural movement of a physical touch and
is what the production virtual-pad button consumes. `input.fly` holds the same
action for its requested finite `durationSeconds` from `0.1` through `10.0`.
The `ACTION_UP` runs in a `finally` path and during cleanup; a failed
release force-stops the bound app session so input cannot remain latched.

For the debug E2E session only, the process-bound locomotion override disables
comfort flight and automatic unsupported-hover while the short jump gesture is
active, then enables comfort flight for the later held action. It never writes
the user's flying or hover preferences; cleanup removes the override.

No avatar state or position is written directly. The adapter does not change
or persist flying preferences or any other user setting.

## Jenkins Phone lab

[`Jenkinsfile`](Jenkinsfile) runs the unchanged `vertical-locomotion` suite
with this Phone adapter on the generic local device-lab agent. The agent must
provide a private executable `OVERTE_ANDROID_ADB` Wi-Fi wrapper. Jenkins binds
only its redacted target alias from Secret Text, reserves the configured
Lockable Resource, publishes the runner's JUnit and sanitized artifacts, and
performs locked cleanup after success, failure, or timeout.
The Phone-scoped [`jenkins_ci.py`](jenkins_ci.py) registers only this suite
with the shared CI helper; the shared runner and suite implementation remain
unchanged.
