<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Fedora physical-device E2E artifacts

The Fedora device lab consumes two independently verified, pre-signed IPAs:

- an opt-in Overte Full Client E2E IPA; and
- the matching preinstalled WebDriverAgent (WDA) IPA from Appium XCUITest.

Linux does not build or sign either package. The manual
`.github/workflows/ios-bootstrap.yml` entrypoint selects the
`fedora_e2e_producer` mode on `refs/heads/apple-ios` and calls the local
`.github/workflows/ios-fedora-e2e-producer.yml` reusable workflow from that
exact revision. The producer reuses the audited `ios-integrated.yml` Full
Client build without credentials, then enters the protected
`ios-fedora-e2e-signing` environment for the short signing phase. It refuses
any other event, caller workflow or ref. Both credential-free build
jobs and the secret-bearing signing job are pinned to GitHub-hosted
`macos-26`; the dispatch surface cannot select a runner. The four Qt checkpoint
inputs must match the deterministic Overte cache and artifact namespaces,
lengths and conservative character allowlist before the reusable build starts.
Inside `ios-integrated.yml`, input values reach shell commands only through
step environment variables.

GitHub only delivers `workflow_dispatch` when the entrypoint exists on the
repository default branch. Therefore `ios-bootstrap.yml` must be registered on
that branch before the Fedora dispatcher can select the `apple-ios` ref. The
reusable producer deliberately has no direct dispatch trigger. Registration
does not broaden signing authority: the called jobs still require the exact
bootstrap caller path and SHA on `refs/heads/apple-ios`, followed by approval of
the branch-restricted signing Environment.

This producer does not install an application, pair a device, reset trust, or
read a device identifier. Those operations remain explicit hardware gates.

## Opt-in application contract

`ios/build-ios.sh configure --platform device --client-graph
--e2e-test-build --bundle-id <dedicated-id>.e2e` selects
`ios/resources/InterfaceE2EInfo.plist.in`. Both the CLI and CMake reject an E2E
build without the Full Client, the device SDK, or a dedicated `.e2e` bundle
identifier. `package-client` rechecks the resulting application.

The E2E Info.plist contains exactly these automation markers:

- `OverteE2ETestBuildContractVersion = 1`; and
- `UIFileSharingEnabled = true`.

The ordinary `InterfaceInfo.plist.in` contains neither key. Normal Release
packaging invokes the same validator in `disabled` mode and fails if either
marker or the compiled E2E-only results-path boundary leaks into a non-E2E
application. The validator checks both the build-tree application and the
finished IPA/ZIP. Conversely, an E2E package must contain both its plist
contract and its compiled opt-in boundary. Only an iOS E2E build resolves and
creates `--testResultsLocation` below the Documents directory. The normalized
path must remain inside Documents, so `..` traversal fails closed; ordinary iOS
and desktop behavior is unchanged.

## Protected producer configuration

Create a GitHub Environment named `ios-fedora-e2e-signing`, restrict its
deployment branch to `apple-ios`, and require the repository's normal signing
reviewers. Configure these Environment secrets:

- `IOS_E2E_SIGNING_P12_BASE64`;
- `IOS_E2E_SIGNING_P12_PASSWORD`;
- `IOS_E2E_APP_PROFILE_BASE64`;
- `IOS_E2E_WDA_PROFILE_BASE64`;
- `IOS_E2E_TEAM_IDENTIFIER`;
- `IOS_E2E_KEYCHAIN_PASSWORD`; and
- `IOS_E2E_LAB_AGE_RECIPIENT`.

The Environment restriction is not a replacement for repository governance.
Before this optional secret-bearing producer is enabled, `apple-ios` must have
branch protection or a ruleset that prevents unreviewed workflow changes.
Environment reviewers must not be able to approve their own deployment, and
administrator bypass must follow the repository's documented emergency policy.
If any of these controls is absent, leave the signing secrets unconfigured and
use only the credential-free Personal Team signing-kit path.

The application profile must authorize the Overte workflow bundle ID. The WDA
profile must authorize both the Appium base ID and its installed
`<base-id>.xctrunner` runner. A narrowly scoped, lab-only trailing wildcard such
as `TEAM.org.overte.*` is supported; global `TEAM.*`, embedded wildcards and
multiple wildcards are rejected. The profile must also authorize the intended
lab device. The workflow decodes the signing inputs with mode
0600 below a run-scoped private scratch directory, imports the certificate
into a temporary keychain, and deletes that keychain and all working material
in an unconditional cleanup step. No credential is passed to the reusable
Full Client build job.

The workflow pins and verifies Appium XCUITest 12.8.0, WebDriverAgent 16.8.0,
and the Apache-2.0 Appium resigner 0.3.1. WDA is exported as a standard IPA
whose only application root is
`Payload/WebDriverAgentRunner-Runner.app`. The `wda_bundle_id` workflow input
is Appium's `updatedWDABundleId` base. The signed app and its manifest use the
actual `<wda_bundle_id>.xctrunner` Runner bundle ID. This is the form accepted by
XCUITest's prebuilt-WDA path; the Fedora consumer does not need to perform an
unreviewed extraction.

The workflow additionally pins age 1.2.1 by architecture and SHA-256. The age
recipient is a fixed native `age1...` recipient supplied only by the protected
Environment. Signed bytes and provisioning profiles never cross the upload
boundary in plaintext.

## Artifact and manifest contract

Each signed IPA and its manifest are first placed at the root of a private
inner ZIP. That ZIP is encrypted to the fixed lab age recipient, and the
plaintext IPA, manifest and inner ZIP are deleted before upload. Each GitHub
Actions artifact contains exactly one `.zip.age` file and is retained for one
day. After authenticated download and age decryption, the inner ZIP contains
exactly the IPA and manifest basenames described below. The common manifest
schema is:

```json
{
  "schemaVersion": 1,
  "contract": "overte-ios-fedora-e2e-artifact-v1",
  "kind": "overte-app",
  "sourceRevision": "0123456789abcdef0123456789abcdef01234567",
  "createdAt": "2029-01-01T00:00:00Z",
  "notAfter": "2029-01-02T00:00:00Z",
  "provenance": {
    "repository": "overte-org/overte",
    "repositoryId": 123456,
    "workflow": ".github/workflows/ios-bootstrap.yml",
    "reusableWorkflow": ".github/workflows/ios-fedora-e2e-producer.yml",
    "ref": "refs/heads/apple-ios",
    "runId": 987654,
    "runAttempt": 1
  },
  "artifact": {
    "name": "0001-OverteIOSClient-Release-device-signed.ipa",
    "sha256": "<64 lowercase hex characters>",
    "size": 123
  },
  "bundle": { "id": "org.overte.interface.e2e" },
  "signing": {
    "signed": true,
    "teamIdentifier": "ABCDE12345",
    "applicationIdentifier": "ABCDE12345.org.overte.interface.e2e",
    "profileExpiration": "2030-01-02T00:00:00Z"
  },
  "testBuildContractVersion": 1
}
```

`notAfter` is exactly 24 hours after `createdAt`. Every provisioning profile
covered by the artifact must remain valid through that boundary; Fedora rejects
the pair after it. This contract limit is intentionally shorter than the
embedded Apple profile's own `profileExpiration`.

For `kind = webdriveragent`, `testBuildContractVersion` is replaced by the
toolchain pin and the separately signed embedded XCTest identity:

```json
{
  "toolchain": {
    "xcuitestDriver": "12.8.0",
    "webdriverAgent": "16.8.0"
  },
  "xctest": {
    "bundle": { "id": "org.overte.WebDriverAgentRunner" },
    "signing": {
      "signed": true,
      "teamIdentifier": "ABCDE12345",
      "applicationIdentifier": "ABCDE12345.org.overte.WebDriverAgentRunner",
      "profileExpiration": "2030-01-02T00:00:00Z"
    }
  }
}
```

For the default `updatedWDABundleId` input
`org.overte.WebDriverAgentRunner`, that WDA manifest's `bundle.id` is
`org.overte.WebDriverAgentRunner.xctrunner`; the signing application identifier
uses the same suffixed bundle ID.

The manifest generator verifies the final IPA bytes, archive root, deep code
signature, top-level provisioning profile, team, exact signed application
identifier, profile expiry, bundle ID, Overte markers and 24-hour contract
window. The extracted leaf signing certificate must occur byte-for-byte in the
profile's `DeveloperCertificates` and remain valid beyond that window.
Repository ID, protected branch, registered dispatch workflow, local
reusable producer path, workflow revision, exact run ID and run attempt are
captured from the protected GitHub context;
the unsigned Overte IPA must first match its same-run integrated-build manifest
and SHA-256. For WDA the generator also
verifies `PlugIns/WebDriverAgentRunner.xctest` individually: its Base-ID
Info.plist, signature, team, application identifier and profile authorization
must all match, and those nested values are attested separately. It never copies
`ProvisionedDevices` or any UDID into a manifest or log.

The signed IPA itself necessarily embeds an Apple provisioning profile, which
may contain authorized device identifiers. Only age ciphertext is uploaded;
do not publish decrypted material in a Release or attach it to an issue. The
age identity belongs only in the Fedora/Jenkins lab as a mode-0600 local secret.

## Fedora consumer boundary

A real-device XCUITest session from Fedora requires all of the following:

- a paired, Developer-Mode iOS/iPadOS 18 or newer device;
- an active usbmuxd/libimobiledevice connection;
- Appium Core 3.7.0, XCUITest 12.8.0 and `appium-ios-remotexpc` 5.15.3;
- an active RemoteXPC tunnel;
- explicit `udid` and `platformVersion` capabilities;
- the exact E2E app and WDA IPAs approved by manifest SHA-256; and
- WDA already installed, selected through `usePreinstalledWDA` and the
  producer input as `updatedWDABundleId`; the installed and manifested app is
  `<updatedWDABundleId>.xctrunner` (or use the same approved IPA through
  `prebuiltWDAPath`).

The authenticated downloader receives these structures:

- Actions artifact `ios-fedora-e2e-overte-<run-id>-<attempt>` contains only
  `ios-fedora-e2e-overte-<run-id>-<attempt>.zip.age`. Decryption yields an inner
  ZIP containing `NNNN-OverteIOSClient-Release-device-signed.ipa` and
  `NNNN-OverteIOSClient-Release-device-signed.manifest.json` at its root.
- Actions artifact `ios-fedora-e2e-wda-<run-id>-<attempt>` contains only
  `ios-fedora-e2e-wda-<run-id>-<attempt>.zip.age`. Decryption yields an inner ZIP
  containing `WebDriverAgentRunner-Runner-16.8.0-signed.ipa` and
  `WebDriverAgentRunner-Runner-16.8.0-signed.manifest.json` at its root.

The device identifier belongs only in the device lab's local mode-0600 target
configuration. It is neither a workflow input nor a manifest field. Installation,
Developer Mode, pairing/trust, RemoteXPC tunnel activation, and the first real
Appium session are hardware gates and must not be claimed by device-free CI.

`ios/tools/verify-runtime-candidate.py` accepts the decrypted Overte manifest
format while retaining the legacy signed-candidate format. The older GitHub
iPad acceptance workflow deliberately does not allowlist this producer because
it has no Fedora-lab age identity and must never receive plaintext signing
material. Authenticated download, age decryption, manifest verification and
Jenkins synchronization form the Fedora consumer boundary.
