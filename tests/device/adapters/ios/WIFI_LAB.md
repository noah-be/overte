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

## Controlled entity script consent

The observed installed integer `OverteE2EEntityScriptConsentVersion=1` marker
enables `nativeEntityConsent: {"kind": "ios-documents", "version": 1}` and the
optional `entity-script.review` operation. The scripted-entity module explicitly
requests this operation before requiring actual script execution. A client
without this marker does not advertise it; lack of executed script still fails
the existing behavioral assertions.

The E2E-only native hook opens the existing source-scoped review flow, requires
the displayed production dialog for the exact controlled HTTP script and
current world, and invokes that dialog's real QML Yes action. Its existing
selected signal and Application listener retain ownership of the decision.
The helper never resolves a consent token directly. A fresh, command/PID-bound
native receipt must confirm each UI action; a delivery acknowledgement cannot
substitute. Wrong sources/worlds, invisible or expired dialogs and unexpected
process changes fail. This is UI automation, not proof of a physical consent
button tap or informed human intent. It grants no general entity-script policy.

The module still independently requires downloaded-script preload evidence and
one real world touch to change its own state, activation count and color.
Background/world/account transitions retain the production consent revocation
behavior. The adapter restores the tablet's prior open/closed state.

## Independent entity synchronization

An owned domain fixture may configure the private `collaboration` binding with
its loopback state/edit endpoints, control token, domain UUID and lab domain
URL. The assignment client edits one bounded fixture entity. The shared probe
only reads replicated properties, including its real `lastEditedBy` author,
color and revision. The host joins that private observation to the independent
actor's exact receipt and current connected domain before exporting portable
results. Native author UUIDs remain outside published probe/artifact data.
The domain keeps its UUID across a controlled offline/recovery transition.

## Prepared native upgrade pair

An explicitly prepared private `nativeUpgrade` contract binds the configured
bundle and signing team to two signed device IPAs. Each role (`source` and
`candidate`) records an absolute owned file path, actual SHA-256, source revision
and independently observed client version. All four artifact fields must differ.
The local reviewed signer verifies the signature; the native installation
service independently accepts or rejects the package. Structural archive
checks alone do not establish signature validity or installed-byte identity.

The adapter rejects foreign paths and version pairs before opening a device
session. It transfers freshly verified package bytes only while the configured
app is stopped. Installation must acknowledge the exact prepared digest, and
the upgraded process must independently report the candidate version. The
portable module checks that its changed persisted setting survived the upgrade.
The driver refreshes the actual executable path and Documents service after
installation because the operating system can move the app container. No
uninstall, data reset or fallback to a different bundle is part of this path.
Installation and upgrade retain bounded 240-second operation deadlines.

## Native microphone permission recovery

The explicit `nativePermission` binding is
`{"kind": "ios-settings-ui", "permissionId": "microphone"}`. The local
driver observes the selected installed app's actual switch in system Settings,
requires unique native accessibility elements and verifies Settings' foreground
process before input. Audio mute is not a substitute for OS permission.

The physical iPad terminates the client when this permission changes. The
adapter independently verifies the stopped process and the foreground
replacement, establishes a fresh client probe and returns the exact
`ios-settings-process-restart` recovery receipt. The portable module validates
that its original and replacement identities match that receipt. Unexplained
restarts, snapshot-triggered restarts, stale observations and an unavailable
replacement still fail. Platforms that return no recovery receipt retain the
same-process requirement. The module restores the original permission in its
cleanup block; its bounded 300-second deadline covers both real Settings
transitions and restoration. Complete device qualification remains separate
from host contract tests.

## Domain fixture cleanup

Independent laboratory slots can pass `--voice-peer-resource ipad` to the
fixture orchestrator. This selects a dedicated PC peer lease while the existing
runtime still creates a fresh profile, authenticated loopback controller and
separate transmit/receive Pulse routes for each peer. The iPad Jenkins job must
use its corresponding dedicated PC resource and distinct scene/domain ports.
The default shared reservation and same-slot exclusivity remain in force.

Linux fixture processes inherit a fresh private ownership nonce and the exact
fixture configuration directory. Cleanup includes matching descendants even
when a process has exited or a child creates a new session. Signals use process
descriptors and recheck ownership before delivery to prevent PID reuse from
targeting an unrelated process. Surviving owned descendants fail cleanup rather
than being hidden by successful parent-process termination. Other hosts retain
their existing process-group cleanup.
