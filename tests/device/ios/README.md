# iOS E2E test-build contract

The maintained iOS application target lives on the platform branch
`apple-ios`, while this directory defines the shared integration boundary. The
protected macOS producer on that branch builds the application and
WebDriverAgent; Fedora verifies, installs, launches, monitors, and evaluates
both artifacts. An unsigned artifact is never treated as runnable.

## Dedicated build configuration

Create a non-production configuration and bundle identifier. Merge
[`Info.plist.e2e.fragment.plist`](Info.plist.e2e.fragment.plist) into that
configuration only. Do not add its keys to a release build:

- `OverteE2ETestBuildContractVersion=1` lets the adapter attest that the
  installed application is the intended E2E artifact.
- `UIFileSharingEnabled=true` is required by XCUITest's real-device
  `@bundle-id:documents/...` file-transfer format.

Validate the final, exported plist rather than only the source template:

```bash
python3 tests/device/ios/validate_test_build.py \
  --plist /path/to/OverteE2E.app/Info.plist \
  --bundle-id org.example.overte.e2e
```

Interface already accepts the three primitives needed by this contract:
`--url`, `--testScript`, and `--testResultsLocation`. Relative result paths are
resolved below the app's Documents directory and the probe writes atomically
through `Test.saveObject`. No production source switch or hidden remote command
channel is introduced.

## Appium launch and evidence flow

Configure the disabled iOS entry in
[`../adapters/appium/targets.example.json`](../adapters/appium/targets.example.json)
in a private file. `fixtureOrigin` must exactly match the device-reachable
origin used by the fixture server, normally a fixed LAN address and port. The
server publishes both `scene.json` and the repository-owned
`/overte_e2e_probe.js` resource.

For `scene.load`, the adapter checks the requested URL against that origin,
terminates the app, and calls `mobile: launchApp` with:

```text
--url <controlled-scene-url>
--testScript <fixture-origin>/overte_e2e_probe.js
--testResultsLocation overte-e2e
```

Termination is mandatory because XCUITest ignores new launch arguments and
environment variables when an app is already running. `probe.snapshot` then
uses `mobile: pullFile` with the derived path
`@<bundle-id>:documents/overte-e2e/overte-probe.json`; the common layer rejects
invalid, incomplete, or stale JSON. Target configuration cannot replace the
URL, script, result-path arguments, or Documents transport with an arbitrary
strategy.

The adapter fails closed in three places: configuration must declare the exact
versioned contract, `appium:autoLaunch` must be false, and a physical target
must report both plist keys from its installed app before any operation runs.
Only then may iOS advertise scene, probe, look, movement, and tablet
capabilities. Accessibility identifiers still require an audit of a real QML
tree before the disabled example target is enabled.

## Fully automated Fedora handoff

The protected `apple-ios` producer emits two short-lived, signed IPAs and one
manifest for each: the dedicated Overte E2E application and WebDriverAgent
built from XCUITest 12.8.0 / WDA 16.8.0. Certificates, keys, profiles,
passwords, Apple account sessions, and device identifiers are not repository
inputs and must not occur in a manifest.

For a fully automated Jenkins/Fedora handoff, use a fine-grained GitHub token
with repository Actions read/write. The synchronizer either dispatches the
protected workflow and receives its exact run ID, or consumes an explicitly
selected successful run. It waits for that run only, downloads the two
run/attempt-specific artifacts, validates their GitHub archive digests and
producer provenance, safely extracts them, invokes the verifier below, and
updates a job-private copy of the Appium target file without changing the
private UDID or platform version:

```bash
OVERTE_GITHUB_TOKEN='<Jenkins secret text>' \
OVERTE_IOS_AGE_IDENTITY_FILE='/private/lab-age-identity.txt' \
OVERTE_DEVICE_TARGET_SELECTOR='<private target selector>' \
python3 tests/device/ios/sync_fedora_artifacts.py \
  --destination /private/overte-device-lab/ios/runs \
  --target-config /private/jenkins-job/appium-targets.json \
  --qt-host-cache-key '<audited cache key>' \
  --qt-ios-cache-key '<audited cache key>' \
  --qt-host-artifact-prefix '<audited artifact prefix>' \
  --qt-ios-artifact-prefix '<audited artifact prefix>'
```

Supply the private selector through `OVERTE_DEVICE_TARGET_SELECTOR`, as Jenkins
does, so it never appears in a process command line.

The producer uploads only age-encrypted payloads because an IPA provisioning
profile can contain device identifiers and the repository is public. The age
identity, token, selector, decrypted IPAs, receipt, and populated target file
stay outside the checkout and are never Jenkins artifacts. A run ID may be supplied
with `--run-id` to reuse an unexpired successful protected producer without
dispatching a build. The versioned GitHub API returns the workflow run ID
directly, eliminating ambiguous "latest run" selection.

For an offline or manually transferred pair, bind the exact bytes to a private
Fedora receipt directly:

```bash
python3 tests/device/ios/verify_fedora_artifacts.py \
  --overte-manifest /private/handoff/overte.json \
  --overte-ipa /private/handoff/Overte-E2E-signed.ipa \
  --wda-manifest /private/handoff/wda.json \
  --wda-ipa /private/handoff/WebDriverAgentRunner-signed.ipa \
  --receipt /private/overte-device-lab/ios/fedora-artifacts-receipt.json \
  --rcodesign /private/ios-security-tools/rcodesign-0.29.0/rcodesign
```

The verifier checks SHA-256 and sizes, safe IPA structure, embedded profiles,
the main Mach-O signature cryptographically with the pinned open-source
`rcodesign`, the provisioning-profile CMS signature with OpenSSL, and the
signed CMS team/application/expiration values against the manifest. It also
checks bundle/application identifiers, the Overte plist marker, and the exact
WDA toolchain pair. Merely placing fake `CodeResources` or profile bytes in an
IPA is rejected. The
Appium adapter rechecks the receipt and artifact hashes before creating a new
session. `appium:app` installs Overte and `appium:prebuiltWDAPath` installs WDA;
`appium:usePreinstalledWDA=true` then launches WDA without Xcode.

On Linux, configure the explicit private UDID, exact `platformVersion` (iOS 18
or newer), `updatedWDABundleId`, both IPA paths, and `artifactReceipt` as shown
in the disabled target example. Xcode-only WDA capabilities are rejected.

RemoteXPC needs a root-owned TUN interface. Verify the installed pin without
elevation, then install the privacy-redacting service once:

```bash
python3 tests/device/ios/remotexpc_tunnel.py preflight \
  --appium-home "$APPIUM_HOME"
sudo python3 tests/device/ios/remotexpc_tunnel.py install-unit \
  --appium-home "$APPIUM_HOME"
python3 tests/device/ios/remotexpc_tunnel.py status
```

`preflight` audits the user-owned Appium source installation but does not attest
the system service. `install-unit` is an explicit, one-time root operation that
must be run from an audited, quiescent checkout and Appium installation. It
copies the wrapper, toolchain lock, pinned Node executable, and complete npm
runtime into the new version directory
`/usr/local/lib/overte-ios-remotexpc/5.15.3`, verifies the copy did not change
during staging, removes every write bit, and atomically publishes it. It never
updates an existing version directory in place. The systemd unit executes only
that root-owned copy, hides home directories, enables `NoNewPrivileges`, and
bounds the service to `CAP_NET_ADMIN`.

`status` attests that immutable installed runtime rather than `$APPIUM_HOME`,
then checks the localhost registry on port 42314. The wrapper reconnects
dropped tunnels and redacts device-token shapes before journal output. A
version change is a new audited installation gate; remove obsolete immutable
versions only as a separate host-administration action after the unit has moved
to the new version.

GitHub API contracts used by the synchronizer:

- [Create a workflow dispatch event](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [List workflow-run artifacts](https://docs.github.com/en/rest/actions/artifacts#list-workflow-run-artifacts)
- [Download an artifact](https://docs.github.com/en/rest/actions/artifacts#download-an-artifact)

## Platform boundary

The runner, adapter, probe, fixture, Appium server, XCUITest driver, and
RemoteXPC transport are open source. The Fedora security boundary additionally
pins age 1.2.1 and Apple Codesign/`rcodesign` 0.29.0 by archive and extracted
executable SHA-256. Apple Xcode and code
signing/provisioning remain proprietary producer prerequisites. A local Mac is
not required: real devices on iOS 18 or newer can be controlled from Fedora
using a prebuilt signed WDA. Simulators and creation/signing of those artifacts
still require macOS/Xcode. Developer Mode, device trust, and the intended real
device remain hardware gates.

Primary protocol references:

- [XCUITest `mobile: launchApp`](https://appium.github.io/appium-xcuitest-driver/latest/reference/execute-methods/#mobile-launchapp)
- [XCUITest file transfer](https://appium.github.io/appium-xcuitest-driver/latest/guides/file-transfer/)
- [XCUITest real-device setup](https://appium.github.io/appium-xcuitest-driver/latest/getting-started/device-setup/)
- [XCUITest from non-macOS hosts](https://appium.github.io/appium-xcuitest-driver/latest/guides/non-macos-hosts/)
- [Preinstalled WebDriverAgent](https://appium.github.io/appium-xcuitest-driver/latest/guides/run-preinstalled-wda/)
