# Android ADB adapters

`phone.json` and `pico.json` expose the existing unattended ADB behavior through
the universal adapter protocol. They discover only authorized targets matching
their runtime profile and never persist the ADB selector.

The adapters provide install, launch, process, foreground, lifecycle, and
telemetry operations. For a debug APK built with the repository's shell-only
E2E launcher, set `OVERTE_ANDROID_E2E_DEBUG=1` to add `scene.load` and
`probe.snapshot`. That launcher maps the common requested fixture to embedded,
repository-owned scene/probe assets and writes the snapshot under the app's
external-files `overte-e2e` directory. Release APKs never advertise this path.

Pico OpenXR input capabilities are disabled by default. A lab that has passed
the hardware gates may explicitly set all of:

- `OVERTE_ANDROID_E2E_DEBUG=1` for the E2E Debug APK;
- `OVERTE_PICO_OPENXR_INPUT=1` to opt into the packaged explicit layer;
- `ANDROID_ADB_SERVER_PORT` to a non-default, Pico-only ADB server;
- either a private (mode `0700`) `OVERTE_PICO_OPENXR_STATE_DIR` or a valid
  private `XDG_RUNTIME_DIR`.

Only then does the Pico adapter advertise `input.look`, `input.move`,
`tablet.open`, and `tablet.close`. The validated port is passed as an explicit
`adb -P` argument for discovery, installation, launch, process/probe calls,
cleanup, and the OpenXR transport; the phone adapter retains the default ADB
command. The adapter keeps one nonce and monotonically increasing sequence
across its short-lived CLI processes, binds it to the one E2E launcher process,
requires a native neutral window between input commands, and fails closed if
the PID/start-ticks identity changes. It removes the grant before the one final
app shutdown. By default the isolated Pico run also snapshots the current
system brightness and brightness mode, selects manual brightness `0` before the
launcher starts, and restores both values during cleanup. That display state is
kept only in the private adapter state directory. Selectors and nonces are never
stored in artifacts or returned by an operation.

The Debug-only explicit OpenXR layer and private host transport are implemented
under `tests/device/openxr_input`; lower-level device gates can also exercise
bounded controller buttons, sticks, triggers, grips, and poses without exposing
a generic OpenXR or shell surface. See `PICO4_CONTROLLER_AUTOMATION.md` for the
capability matrix and required physical-device evidence. Phone/iPad touch
automation remains owned by the Appium adapter.

The older `phone-device-test.sh` and Pico release-acceptance scripts remain
packaging/release gates. Their runtime primitives are represented here without
weakening their APK provenance and confirmation checks.
