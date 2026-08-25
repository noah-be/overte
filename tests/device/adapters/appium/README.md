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

For iOS 18+ the Fedora adapter requires an explicit private `udid`, fixed
`platformVersion`, `usePreinstalledWDA=true`, `enforceAppInstall=false`, and
`updatedWDABundleId`. `webDriverAgentUrl` and Xcode-only capabilities are
rejected. Strong `signed-ipa` receipts bind the Overte IPA, WDA IPA, and a
safely extracted `WebDriverAgentRunner-Runner.app`; `prebuiltWDAPath` points to
that tree, whose relative paths, executable bits, and file contents are hashed.
The distinct `personal-team-preinstalled` receipt requires no artifact path,
rejects both path capabilities if present, and explicitly carries
`cryptographicByteBinding=false`; it never silently falls back to the strong
mode. Signing remains a manual Apple/Sideloadly boundary or an optional
protected macOS-producer boundary. Jenkins receives no Apple credentials.
