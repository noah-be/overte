# Native iPad lab extension

[`IOSAdapter`](adapter.py) extends the [base Appium adapter](../appium/README.md)
for an authenticated physical-device driver. The driver must implement actual
`mobile: overteProcessInfo` and `mobile: overteAbortApp` operations for the
configured application. Process identity and foreground observations come
from the device, including after lifecycle operations.

Owned HTTP commands deliver asset creation, domain navigation, audio mute,
and the allow-listed audio warning setting to the shared in-client probe.
Delivery alone is insufficient: the adapter requires an exact fresh
`client-command-result.json` receipt from the running client's Documents
directory. The portable modules independently verify the resulting behavior.

## Native UI observation

An installed E2E client may expose the integer Info.plist marker
`OverteE2ENativeUiObservationVersion=1`. Only fresh authenticated installation
inventory may enable the optional target configuration:

```json
"nativeUiObservation": {"kind": "uikit-documents", "version": 1}
```

That test-only client exposes `Test.iosNativeUiSnapshot()` when launched with
the existing explicit test script and results directory. The shared probe
saves its read-only UIKit observation as `ios-native-ui.json`. The adapter
requires an exact schema, current sample, matching live foreground PID, and
the closed Tablet Contract vocabulary. Absent controls remain absent; the
observer never fills in expected controls or exports account/user text.

The audit XML represents observed UIKit controls. It is not an XCTest tree.
Physical activation uses a WDA touch at the center of the freshly observed
visible enabled control's native frame, followed by contact release even if
the touch request fails. The module still observes the actual resulting
tablet screen independently. No fixed-coordinate activation fallback is used.

The optional path needs a newly built and installed client plus successful
physical-device validation. Host regression success alone does not establish
device support. A client without the installed marker retains the base
Appium observation path and any transport capability exclusions.

## Local regression checks

From the repository root:

```sh
python3 tests/run-unittest-suite.py tests/device/self_tests --pattern test_ios_native_ui.py
python3 tests/run-unittest-suite.py tests/device/self_tests --pattern test_ios_probe_observation.py
python3 tests/run-unittest-suite.py tests/device/self_tests --pattern test_ios_extended_adapter.py
```

These regressions are included in the quick device control-plane profile.
The complete real-device run must still require all 35 catalog modules and
retain the tested client and runner versions.
