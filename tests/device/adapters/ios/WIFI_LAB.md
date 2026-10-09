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

iOS `Test.saveObject` publishes a complete JSON file with an atomic rename.
The native AFC reader opens the file first and reads bounded current bytes
until EOF, without pairing an earlier path-size query with a later file body.
This keeps rapidly updated observations complete while the service connection
is reused. Parse, schema, freshness and process-identity checks remain required.

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

## Native text and rendering integration

The exact installed integer `OverteE2ENativeWorldTapVersion=1` marker enables
physical primary input. The owned fixture temporarily selects first-person
camera mode and restores the prior mode afterwards. A read-only observer
projects the unique controlled entity through the actual camera frustum and
requires the client ray pick to hit that entity before the host sends a real
touch. The portable modules independently check the resulting input event and
entity-script mutation. No fixture command can set an input count or target
screen coordinate.

The exact installed integer `OverteE2ENativeIntegrationVersion=2` marker enables
`nativeIntegration: {"kind": "ios-documents", "version": 2}`. Text setup uses a
dedicated test panel containing the product `Uit.TextField`; only focus, clear,
read and dismiss are available to the test bridge. Actual Unicode, backspace
and submit events come from XCTest. GUI-thread observations must match the
command nonce, foreground process and freshness bound. Typed values and submit
counters are never supplied by the host observer.

Renderer observations use the active Vulkan plugin, actual physical-device
properties and current world-generation presentation records from the real
WSI queue. The host additionally classifies a bounded contemporaneous physical
screenshot of the central world region. A counter or a lit edge toolbar alone
does not prove healthy visible rendering. Pillow is required for this local
physical screenshot analysis. These operations still require native build,
installation and real-device qualification.

## Independent entity synchronization

An owned domain fixture may configure the private `collaboration` binding with
its loopback state/edit endpoints, control token, domain UUID and lab domain
URL. The assignment client edits one bounded fixture entity. The shared probe
only reads replicated properties, including its real `lastEditedBy` author,
color and revision. The host joins that private observation to the independent
actor's exact receipt and current connected domain before exporting portable
results. Native author UUIDs remain outside published probe/artifact data.
The domain keeps its UUID across a controlled offline/recovery transition.
