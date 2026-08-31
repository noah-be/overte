# Android ADB adapters

`phone.json` and `pico.json` expose the existing unattended ADB behavior through
the universal adapter protocol. They discover only authorized targets matching
their runtime profile and never persist the ADB selector.

The adapters provide install, launch, process, foreground, lifecycle, and
telemetry operations. For a debug APK built with the repository's shell-only
E2E launcher, set `OVERTE_ANDROID_E2E_DEBUG=1` to add `scene.load` and
`probe.snapshot`. That launcher maps the common requested fixture to embedded,
repository-owned scene/probe assets and writes the snapshot under the app's
private `overte-e2e` directory. Release APKs never advertise this path.

`navigation.enter-domain`, `asset.load`, and `sound.play` have a stricter
runtime gate. They are advertised only while the debug launcher process is
running, its app-private marker matches `android-debug-file-v1`, and its probe
is both fresh and reporting the same channel contract. Every command is
argument-validated and atomically committed with `run-as`; the adapter confirms
the command bytes and unchanged PID/start ticks but leaves behavioral success
to the independent probe and fixture HTTP telemetry. Domain navigation assigns
the exact requested `hifi` URL in the existing process. Asset loading creates
one local controlled Image entity. Sound binds the probe to the validated
fixture command endpoint and posts the exact command ID and sound URL. A normal
production launch, stale or missing probe, unavailable `run-as` channel, or
process change exposes none of these capabilities and rejects direct invokes.

Pico OpenXR input capabilities are disabled by default. A lab that has passed
the hardware gates may explicitly set all of:

- `OVERTE_ANDROID_E2E_DEBUG=1` for the E2E Debug APK;
- `OVERTE_PICO_OPENXR_INPUT=1` to opt into the packaged explicit layer;
- `ANDROID_ADB_SERVER_PORT` to a non-default, Pico-only ADB server;
- either a private (mode `0700`) `OVERTE_PICO_OPENXR_STATE_DIR` or a valid
  private `XDG_RUNTIME_DIR`.

Only then does the Pico adapter advertise `input.look`, `input.move`,
`input.jump`, `input.fly`, `tablet.open`, and `tablet.close`. Jump and flight
are Pico bindings for the shared semantic operations: a bounded right-secondary
press performs a jump and a bounded hold enters upward flight. The validated
port is passed as an explicit `adb -P` argument for discovery, installation,
launch, process/probe calls,
cleanup, and the OpenXR transport; the phone adapter retains the default ADB
command. The adapter keeps one nonce and monotonically increasing sequence
across its short-lived CLI processes, binds it to the one E2E launcher process,
requires a native neutral window between input commands, and fails closed if
the PID/start-ticks identity changes. It removes the grant before the one final
app shutdown. It deliberately leaves Pico display brightness and brightness
mode untouched because changing either can alter the XR execution cadence.
Selectors and nonces are never stored in artifacts or returned by an operation.

The Debug-only explicit OpenXR layer and private host transport are implemented
under `tests/device/openxr_input`; lower-level device gates can also exercise
bounded controller buttons, sticks, triggers, grips, and poses without exposing
a generic OpenXR or shell surface. See `PICO4_CONTROLLER_AUTOMATION.md` for the
capability matrix and required physical-device evidence. Phone/iPad touch
automation remains owned by the Appium adapter.

The Pico adapter deliberately does not advertise `accessibility.snapshot`.
Overte's Pico UI is rendered through an OpenXR surface, for which the laboratory
has no audited native Android accessibility tree. Jenkins rejects
`RUN_ACCESSIBILITY=true` with `android-pico-adb` instead of skipping the module
or manufacturing accessibility evidence. A dedicated VR accessibility contract
can be added separately if the product defines one.

The older `phone-device-test.sh` and Pico release-acceptance scripts remain
packaging/release gates. Their runtime primitives are represented here without
weakening their APK provenance and confirmation checks.
