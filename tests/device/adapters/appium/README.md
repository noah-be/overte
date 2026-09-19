# Appium Android and iOS adapters

The adapter talks directly to Appium's W3C HTTP protocol using the Python
standard library. No proprietary device cloud or language-specific Appium
client is required.

Copy `targets.example.json` outside the repository, insert private UDIDs and
verified control identifiers, protect the file, and export
`OVERTE_APPIUM_TARGETS=/absolute/private/targets.json`. Capabilities are
advertised only when their corresponding control or probe transport exists.
The path must already be absolute, must not cross symlinks or point back into
the checkout, and on POSIX the ordinary current-user-owned file must have mode
`0600`. Session metadata is stored through an equally private atomic file.

The shared `app.install` operation accepts only an absolute regular artifact
path and invokes Appium's standard `mobile: installApp` command. Unsupported
operations and malformed arguments are rejected before creating or contacting
a WebDriver session.

An enabled physical Android target is attested as an authorized ARM64 touch
phone before Appium creates a session. The gate rejects emulators and Android
watch, TV, automotive, VR, Pico, or ByteDance identities, and requires the
minimum API and OpenGL ES levels used by the phone client. Jenkins freezes only
the credential-selected Phone entry into a mode-0600 per-build target file so
another lab job cannot change its ADB, probe, or controlled-command contract
between fresh sessions. `app.install` repeats the same phone attestation before
invoking Appium's install command.

For Android, `process.kind=adb` obtains a real PID/start-time identity from the
physical device selected by `appium:udid`. Appium alone does not expose a
trustworthy Android process identity. The same observer supplies Android
battery, memory, and thermal telemetry for the stability suite. On iOS the
adapter uses XCUITest's
active-app PID and attests that a target marked `physical` is not a simulator.
The configured iOS `appId` must equal `appium:bundleId`.

Run the `accessibility` suite before enabling `e2e-core`. Its artifact records
the actual native tree exposed by QML. Replace the example tablet identifiers
only after that audit; placeholder identifiers are not acceptance evidence.
If a target's Qt build exposes no actionable QML nodes, configure the audited
normalized `togglePoint`, or distinct `openPoint` and `closePoint`, instead.
This touch fallback can verify tablet behavior through the probe, but it does
not make the separate Accessibility gate pass.

After the native tree has been audited against `tablet-ui-contract.json`, a
target may opt into `tablet.snapshot` and `tablet.activate` with exactly
`"semanticUi": {"contractVersion": 1}`. The adapter reduces Android resource
IDs/content descriptions or iOS prefixed accessibility identifiers to the
closed shared vocabulary, rejects ambiguous trees, and activates only a
visible enabled control. Merely configuring open/close coordinates does not
advertise the semantic operations.

The Android example uses `scene.kind=android-debug-e2e`. This starts the
shell-protected launcher that exists only in debug APKs; the launcher copies
the repository-owned scene and probe assets into app-private storage and never
accepts raw argv or an external scene URL. The fresh probe result stays in
app-private storage and is read through Android's debug-only `run-as` boundary;
the adapter does not grant broad storage access. Keep this scene and probe
configuration absent for release APKs.

The three domain, asset, and sound capabilities are advertised on Android only
when the physical debug target also configures the fixed
`clientControl.kind=android-run-as-command` path shown in the example. Commands
are atomically written inside the app sandbox. The adapter checks the exact ADB
PID/start-time identity, foreground state, and Appium session before and after
delivery. `sound.play` additionally requires the exact fixture
`/sound-command.json` endpoint on the same origin as the sound resource; the
probe observes the real client audio state rather than an adapter simulation.

The disabled iOS example implements the fail-closed
`overte-ios-e2e-v1` contract described in [`../../ios/`](../../ios/). For a
physical target the adapter checks the installed app's test-only plist marker
and `UIFileSharingEnabled` before executing any command. It accepts a scene only
from the configured fixture origin. An initial `app.launch` supplies only the
audited test-build arguments; after backgrounding, `app.launch` merely
reactivates the existing process so lifecycle tests retain the PID. `scene.load`
is the explicit restart boundary: it terminates the app so new scene arguments
take effect, supplies Interface's existing `--url`, `--testScript`, and
`--testResultsLocation` arguments, and pulls the fresh result from the derived
`@bundle-id:documents/...` path. A normal iOS target without that exact contract
may advertise lifecycle and Accessibility capture, but configuration of scene,
probe, or behavioral controls is rejected.

Android requires Appium plus the open-source UiAutomator2 driver. For iOS 18+
the Fedora adapter uses the pinned open-source RemoteXPC transport and a
prebuilt signed WDA; it requires explicit `udid`, `platformVersion`,
`usePreinstalledWDA`, and `updatedWDABundleId` capabilities. Supplying local
Overte/WDA artifact paths additionally requires the private, hash-bound receipt
created by [`../../ios/verify_fedora_artifacts.py`](../../ios/verify_fedora_artifacts.py).
The app and WDA are still built and signed with Apple's proprietary Xcode and
provisioning stack on the protected macOS producer, but no local macOS test
agent is required.
