# Appium iOS adapter

The adapter talks directly to Appium's W3C HTTP protocol using the Python
standard library. No proprietary device cloud or language-specific Appium
client is required.

Copy `targets.example.json` outside the repository, insert private UDIDs and
verified control identifiers, protect the file, and export
`OVERTE_APPIUM_TARGETS=/absolute/private/targets.json`. Capabilities are
advertised only when their corresponding control or probe transport exists.

The adapter uses XCUITest's active-app PID and attests that the configured
target is physical rather than a simulator.
The configured iOS `appId` must equal `appium:bundleId`.

The mandatory `e2e-core` baseline is the first application run. An optional
`accessibility` audit runs afterward in its own clean session. Its public
artifact contains only counts and the explicitly requested identifiers; raw
XML and any user/account text from the native tree are not archived. Keep the
disabled example disabled until that hardware audit succeeds. The product identifiers are
`OverteTabletOpen` and `OverteTabletClose`; iOS rejects alternatives and all
tablet coordinate fallbacks. The hardware audit must still prove both appear
as actionable nodes on the signed device build.

The disabled iOS example implements the fail-closed
`overte-ios-e2e-v1` contract described in [`../../ios/`](../../ios/). For a
physical target the adapter validates one exact private receipt contract and
keeps `autoLaunch=false`. Strong signed-IPA mode asks the immutable helper to
replace WDA and Overte from the receipt-bound IPAs. Both modes then run its
InstallationProxy preflight before `POST /session`. Neither helper exposes the
device identity. The preflight checks installed Overte/WDA IDs,
signing/profile evidence, Overte's test marker and file sharing, plus WDA
16.8.0/XCUITest 12.8.0 markers. Post-session `listApps`
repeats the application/WDA contract check before the first launch.
That one launch supplies the fixed repository scene URL, probe URL and private
results location through Interface's existing `--url`, `--testScript`, and
`--testResultsLocation` arguments. `scene.load` only validates that same URL,
foreground state and PID without a lifecycle command. Look, move, tablet and Documents `pullFile`
all require the originally observed PID and bundle. A PID change is a product
failure; malformed Appium/XCUITest evidence is an infrastructure failure.

`sound.play` is advertised only when the target also has the exact
`soundControl.kind=fixture-http` configuration from the example. The sound and
command URLs must share the configured fixture origin, the endpoint must be
`/sound-command.json`, and the fixture must acknowledge the exact versioned
payload. WDA verifies the original foreground PID before and after the request;
audio readiness and playback remain observations of the real probe. iOS does
not advertise `navigation.enter-domain` or `asset.load`: the current test build
has no stable in-client control channel for live location changes or entity
creation, and WDA UI gestures/text input are not accepted substitutes.

The optional iOS `verticalLocomotion` control drives the rendered Overte
virtual-pad Jump button, not a private test hook. Its fractional `jumpPoint`
must be copied into private target configuration only after the real landscape
control position has been audited; the adapter has no coordinate fallback. A
single 50–100 ms bounded press implements `input.jump`; longer configured
presses are rejected before Appium can reach Overte's 500 ms hold-to-fly
threshold. `input.fly` follows Overte's
normal double-jump gesture and holds the second press for the contract's
`durationSeconds` value. Both operations guard the original foreground PID
before and after the W3C touch sequence. The checked-in example values describe
the product's current safe-content fallback layout and are not device evidence.

For iOS 18+ the Fedora adapter requires an explicit private `udid`, fixed
`platformVersion`, `usePreinstalledWDA=true`, `enforceAppInstall=false`, and
`updatedWDABundleId`. `webDriverAgentUrl` and Xcode-only capabilities are
rejected. Strong `signed-ipa` receipts bind the Overte IPA, WDA IPA, and a
safely extracted `WebDriverAgentRunner-Runner.app`; `prebuiltWDAPath` points to
that tree, whose relative paths, executable bits, and file contents are hashed.
The distinct `personal-team-preinstalled` receipt requires no artifact path,
rejects both path capabilities if present, and explicitly carries
`cryptographicByteBinding=false`; it never silently falls back to the strong
mode. It may bind either the fixed IDs or one uniquely marker-selected
Sideloadly-remapped pair. For a remapped suffixless WDA it binds
`updatedWDABundleIdSuffix=""` as well as the full installed ID. Every later
session rechecks those exact receipt-bound IDs rather than rediscovering apps.
Signing remains a manual Apple/Sideloadly boundary or an optional protected
macOS-producer boundary. Jenkins receives no Apple credentials.

Runtime revision 12 starts the preinstalled WDA on Fedora through the pinned
pymobiledevice3 XCTest/testmanagerd handshake and the already attested RSD
endpoint. It keeps WDA alive for the Appium session and releases the XCTest
completion event during shutdown so all DTX providers close before another
runner starts. This replaces revision 9's out-of-band Home-event workaround.
Artifact synchronization removes a stale `iosSessionBootstrap` section from
private targets so it cannot race the real XCTest launch. The Fedora path uses
the fixed WDA port and bounded process execution; custom Xcode-only or WDA
launch-environment capabilities remain unsupported. iOS cleanup additionally
terminates and verifies the exact app over DVT, so a lost Appium/WDA session
cannot leave Overte running.
