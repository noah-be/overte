<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Fedora iOS E2E handoff and immutable runtime

This directory is the Fedora half of the protected iOS device-lab boundary.
Fedora never builds or signs an IPA. It consumes only the two age-encrypted
artifacts produced by the protected `apple-ios` workflow, verifies their exact
GitHub run and attempt, verifies the exported signatures and profiles, then
activates a private Appium target outside the checkout.

Two explicitly separate Personal-Team paths are also supported. `local-import`
cryptographically verifies two exported signed IPAs. The weaker
`personal-team-preinstalled` mode observes apps already installed by Sideloadly
and never claims that their bytes derive cryptographically from the unsigned kit.

No IPA, provisioning profile, age identity, GitHub token, receipt, target
selector, UDID, platform version, or decrypted diagnostic belongs in Git.

## Exact open-source pins

[`toolchain.lock.json`](toolchain.lock.json) and the complete npm
[`package-lock.json`](package-lock.json) pin:

- Appium Core 3.7.0;
- Appium XCUITest Driver 12.8.0;
- WebDriverAgent 16.8.0;
- Appium iOS RemoteXPC 5.15.3;
- Appium iOS Device 3.1.21 for the pre-session InstallationProxy check;
- Node.js 24.19.0 and npm 11.17.0;
- age 1.2.1; and
- Apple Codesign/`rcodesign` 0.29.0.

Every npm resolution is HTTPS-registry-bound and has a SHA-512 SRI value. The
four direct npm artifacts additionally have registry SHA-1 and independently
computed SHA-256 values. Validate the repository lock and the local host with:

```bash
python3 tests/device/ios/validate_toolchain_lock.py --check-host
```

The Fedora host additionally needs OpenSSL, `python3-pyyaml`, usbmuxd,
libimobiledevice, and `/dev/net/tun`. The physical device must run iOS/iPadOS 18
or newer, be paired and trusted, and have Developer Mode enabled.

## Authenticated producer selection

The registered dispatch entry is `.github/workflows/ios-bootstrap.yml`. It is
dispatched on `apple-ios` with `fedora_e2e_producer=true` and calls the local
reusable `.github/workflows/ios-fedora-e2e-producer.yml` from the same commit.
The GitHub API request sets `return_run_details=true`; the returned
`workflow_run_id` is the only run that is polled. There is no list-runs or
"latest successful" fallback.

For a new producer run, keep the token and target selector in the environment:

```bash
OVERTE_GITHUB_TOKEN='<Actions read/write token>' \
OVERTE_IOS_AGE_IDENTITY_FILE='/private/ios-lab/age-identity.txt' \
OVERTE_DEVICE_TARGET_SELECTOR='<private selector>' \
python3 tests/device/ios/sync_fedora_artifacts.py \
  --destination /private/ios-lab/runs \
  --target-config /private/jenkins-job/appium-targets.json \
  --qt-host-cache-key '<audited cache key>' \
  --qt-ios-cache-key '<audited cache key>' \
  --qt-host-artifact-prefix '<audited artifact prefix>' \
  --qt-ios-artifact-prefix '<audited artifact prefix>'
```

To reuse an unexpired run, both the run and attempt are mandatory:

```bash
OVERTE_GITHUB_TOKEN='<Actions read token>' \
OVERTE_IOS_AGE_IDENTITY_FILE='/private/ios-lab/age-identity.txt' \
python3 tests/device/ios/sync_fedora_artifacts.py \
  --destination /private/ios-lab/runs \
  --run-id 123456789 --run-attempt 1
```

The synchronizer requires the exact repository name and numeric repository ID,
Bootstrap workflow path, protected branch/ref, source SHA, run ID, run attempt,
artifact names, artifact IDs, archive URLs, archive SHA-256 digests, and matching
manifest provenance. A rerun cannot silently replace a selected attempt.

## Explicit public Personal-Team kit and private handoff

Never select an unsigned kit by "latest". GitHub requires an Actions-read token
even for this public artifact download. Keep it only in the environment and
either dispatch the registered Bootstrap workflow with all four audited Qt
checkpoint coordinates:

```bash
OVERTE_GITHUB_TOKEN='<Actions read/write token>' \
python3 tests/device/ios/fetch_personal_team_kit.py \
  --qt-host-cache-key '<audited host cache key>' \
  --qt-ios-cache-key '<audited iOS cache key>' \
  --qt-host-artifact-prefix '<audited host artifact prefix>' \
  --qt-ios-artifact-prefix '<audited iOS artifact prefix>' \
  --destination /private/ios-lab/public-kit-new-run
```

This sends `personal_team_e2e_kit=true` and `return_run_details=true`, accepts
only the returned run ID at attempt 1, and polls only that run. Alternatively,
fetch one already completed, explicit Bootstrap run and attempt:

```bash
OVERTE_GITHUB_TOKEN='<Actions read token>' \
python3 tests/device/ios/fetch_personal_team_kit.py \
  --run-id 123456789 --run-attempt 1 \
  --destination /private/ios-lab/public-kit-123456789-1
```

The fetched files are unsigned public data (0644). Before private import, copy
the reviewed manifest as well as both signed exports into mode-0600 private
state outside the checkout. If Sideloadly provides signed IPA exports, create
`personal-team-signed-handoff.json` with the producer helper and run:

```bash
OVERTE_DEVICE_TARGET_SELECTOR='<private selector>' \
python3 tests/device/ios/sync_fedora_artifacts.py local-import \
  --unsigned-kit /private/ios-lab/input/personal-team-e2e-kit.json \
  --attestation /private/ios-lab/input/personal-team-signed-handoff.json \
  --overte-ipa /private/ios-lab/input/Overte-PersonalTeam-E2E-signed.ipa \
  --wda-ipa /private/ios-lab/input/WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa \
  --destination /private/ios-lab/runs \
  --target-config /private/jenkins-job/appium-targets.json
```

If Sideloadly installs directly and exports no signed IPAs, create the short
private observation only under the exclusive device lock:

```bash
chmod 0600 /private/ios-lab/input/personal-team-e2e-kit.json
python3 tests/device/ios/create_preinstalled_attestation.py \
  --unsigned-kit /private/ios-lab/input/personal-team-e2e-kit.json \
  --output /private/ios-lab/input/personal-team-preinstalled-attestation.json \
  --device-observed --installed-with-sideloadly \
  --fixed-bundle-identifiers-confirmed \
  --accept-no-cryptographic-byte-binding

OVERTE_DEVICE_TARGET_SELECTOR='<private selector>' \
python3 tests/device/ios/sync_fedora_artifacts.py personal-team-preinstalled \
  --attestation /private/ios-lab/input/personal-team-preinstalled-attestation.json \
  --destination /private/ios-lab/runs \
  --target-config /private/jenkins-job/appium-targets.json
```

Use `--fixed-bundle-identifiers-confirmed` only when the installed IDs were
preserved. If Sideloadly remapped the two IDs because the Personal-Team quota
was already occupied, replace that flag with
`--accept-sideloadly-bundle-id-remapping`. The immutable helper then queries
all user apps, requires exactly one Overte E2E-marker candidate and one pinned
WDA/XCUITest-marker candidate, verifies their profiles/application identifiers
and common signer/team, and binds the observed IDs into the private receipt.
It rejects ambiguous candidates and never publishes the discovered values.

The latter invokes the root-attested InstallationProxy helper. It checks the
selected IDs, signed application/team entitlements, equal team/signer identity,
`ProfileValidated`, the Overte E2E markers, and the exact WDA/XCUITest version
markers. It does not prove installed byte hashes, profile
expiration, or successful WDA launch; those remain session/hardware gates.

Both Actions archives must contain exactly one non-compressed `.zip.age` member.
Authenticated age decryption yields an exact, non-compressed IPA/manifest pair.
Traversal, links, special files, encryption flags, duplicates, unexpected names,
compression, oversized entries, cumulative expansion, and actual copy overruns
fail closed. Temporary ciphertext and plaintext are removed on success, error,
timeout, and interruption. Successful decrypted IPAs remain only in the private
run directory for the short duration of the Jenkins device job.

## IPA and signing verification

[`verify_fedora_artifacts.py`](verify_fedora_artifacts.py) validates both final
IPA bytes and creates a mode-0600 receipt. It verifies:

- exact manifest fields, 24-hour validity window, source revision, and producer
  provenance;
- IPA SHA-256, size, safe structure, bundle ID, application ID, and E2E plist
  markers;
- XCUITest 12.8.0 / WDA 16.8.0 and the signed Runner/nested XCTest pair;
- each main Mach-O CMS/code-directory signature with pinned `rcodesign`;
- the signed code-directory identifier, Apple signer team, XML entitlements,
  DER entitlements, application identifier, and team entitlement;
- each embedded provisioning-profile CMS signature with OpenSSL;
- exact profile team, application authorization, expiration, and byte-for-byte
  membership of the actual Mach-O leaf certificate in `DeveloperCertificates`;
  and
- signer/profile lifetime through the complete handoff window.

`rcodesign 0.29.0` documents that its standalone verifier is not an Apple policy
validator and does not verify external CodeResources slots. Fedora therefore
does not treat `rcodesign verify` alone as sufficient: protected GitHub archive
digests and manifest IPA SHA-256 bind every resource byte, while signed
code-directory/CMS identity, entitlements, leaf certificate, and profile are
checked independently. Any resource mutation after the producer changes both
the Actions digest and manifest-bound IPA hash.

The resulting receipt has exactly these top-level fields:

```text
schemaVersion, contract, sourceRevision, createdAt, notAfter,
provenance, overte, wda, toolchain
```

`provenance` contains `repository`, `repositoryId`, `workflow`,
`reusableWorkflow`, `ref`, `runId`, and `runAttempt`. The private Appium target
update is atomic and preserves `appium:udid`, `appium:platformVersion`, and the
fixed `testBuild.scenePath`. It sets only verified artifact identity/path fields,
`enabled=true`, `appium:autoLaunch=false`, and
`appium:usePreinstalledWDA=true`. Xcode signing capabilities are rejected on
Fedora.

For both signed modes, `overte` is exactly `{path, sha256, bundleId}`. `wda` is
exactly `{ipaPath, ipaSha256, prebuiltPath, prebuiltTreeSha256, bundleId}`. The
WDA IPA remains the receipt-bound InstallationProxy input; `prebuiltPath` is the
safely extracted `WebDriverAgentRunner-Runner.app` required by Appium 12.8.0.
Its canonical tree hash sorts POSIX relative paths bytewise. A directory adds
`D NUL path NUL`; a file adds `F NUL path NUL`, `X` when any executable bit is
set (otherwise `-`), and the 32 raw SHA-256 bytes of its contents. Symlinks,
hard-linked files, and special files are rejected. The verifier, immutable
installer, and adapter use the same checked-in implementation.

## One-time immutable RemoteXPC/Appium installation

Prepare one audited staging project outside the checkout as the unprivileged lab
administrator. Copy only the checked-in package files and materialize them with
`npm ci`; do not use `appium driver install latest`:

```bash
install -d -m 0700 /private/ios-lab/appium-staging
install -m 0600 tests/device/ios/package.json \
  tests/device/ios/package-lock.json /private/ios-lab/appium-staging/
npm ci --ignore-scripts --no-audit --no-fund \
  --prefix /private/ios-lab/appium-staging
python3 tests/device/ios/remotexpc_tunnel.py preflight \
  --appium-home /private/ios-lab/appium-staging
```

The exact one-time privileged publication command is:

```bash
sudo python3 tests/device/ios/remotexpc_tunnel.py install-unit \
  --appium-home /private/ios-lab/appium-staging
```

Run it only from an audited, quiescent checkout and staging tree. It atomically
copies the pinned Node executable, package files, complete npm tree, tunnel
wrapper, and toolchain lock into
`/usr/local/lib/overte-ios-remotexpc/5.15.3-r7`. The suffix is the immutable
Overte packaging revision; the pinned RemoteXPC package remains 5.15.3. Source
and destination trees are hashed before publication. Every installed file is
root-owned and immutable. Existing content and modes are only attested, never
modified in place; the host SELinux policy is reapplied idempotently when
SELinux is enabled.

The systemd tunnel service executes only this immutable copy. It has
`NoNewPrivileges`, a `CAP_NET_ADMIN`-only capability boundary, strict filesystem
and home protection, three child reconnect attempts, and a bounded
`Restart=on-failure` policy. Its registry binds locally and status prints only
the aggregate active-tunnel count. Device-shaped tokens are redacted before
journal output. Strongbox registry and pairing state is confined to systemd's
root-owned, mode-0700 `/var/lib/overte-ios-remotexpc` state directory;
`XDG_DATA_HOME` is fixed to that path so `ProtectHome=true` remains effective.
This private state may contain pairing secrets and device-linked filenames. It
must never enter backups, diagnostics, workspaces, or artifacts. When a device
is deprovisioned, stop the unit and remove only its systemd-managed state:

```bash
sudo systemctl stop overte-ios-remotexpc.service
sudo systemctl clean --what=state overte-ios-remotexpc.service
```

The immutable copy also contains three deliberately quiet device helpers. Under
the exclusive Jenkins device lock, a signed-IPA target is handled in this exact
order: attest/mount the pinned Personalized Developer Disk Image, revalidate the
receipt and both IPA hashes, replace WDA and Overte with `device-install`, run
`device-preflight`, then create the Appium session. The
wrapper accepts private values only as JSON on stdin:

```text
remotexpc_tunnel.py device-install
stdin: {"udid":"<private>","receipt":"/absolute/private/receipt.json"}
```

It re-attests the immutable runtime, receipt lifetime/toolchain, mode-0600 IPA
files, and the private WDA app tree before passing the two IPA paths to the
pinned installation-proxy implementation. It removes stale same-version apps,
installs WDA then Overte, and emits only a generic PASS/error. The weaker
`personal-team-preinstalled` mode never invokes this installer; it observes the
already installed apps and proceeds directly to the same marker/team preflight.

Physical iOS/iPadOS 17 and newer also requires Apple's Personalized Developer
Disk Image before WDA can load XCTest. The repository does not redistribute or
automatically download that Apple payload. The operator keeps exactly
`Image.dmg`, `BuildManifest.plist`, and `Image.dmg.trustcache` together in one
external mode-0700 directory, with each file mode 0600. The lock pins the
operator-supplied payload to DeveloperDiskImage commit
`5423e4e955fbb3a9eef3e1212acfbfc6e7a26236`, build `27A5228h`, exact sizes,
SHA-256 values, and manifest SHA-384 bindings. `device-ddi-mount` snapshots the
validated bytes into an ephemeral private directory, suppresses all TSS and
device output, and compares the mounted image signature directly to the pinned
SHA-384 before attesting both XCTest services. Jenkins supplies this
directory through the private `IOS_DDI_ROOT` parameter.

Attest status without elevation:

```bash
python3 /usr/local/lib/overte-ios-remotexpc/5.15.3-r7/remotexpc_tunnel.py status
```

Jenkins must also start Appium from the immutable runtime, never from a mutable
user `node_modules`:

```bash
/usr/local/lib/overte-ios-remotexpc/5.15.3-r7/remotexpc_tunnel.py appium-server \
  --state-root /private/jenkins-job/appium-state \
  --address 127.0.0.1 --port 4723
```

That entry re-attests the whole root-owned tree, fixes `APPIUM_HOME` to an
ephemeral directory below the absolute, symlink-free, caller-owned mode-0700
state root, binds only loopback, and forces error-only, color-free logs. It
copies only the root-attested XCUITest registry and removes the state on exit.
For fixture-backed physical iOS suites, Jenkins creates the potentially slow
Appium/WDA session before entering the common module's 60-second operation
window. `launch-smoke` immediately reuses that persisted session and fails if
the one controlled Overte launch has exited or changed process identity; it
does not launch the application a second time.
Inside a hardened user-systemd namespace, host UID 0 is accepted only when it
appears as the kernel-configured overflow UID; arbitrary remapped ownership is
rejected. The exact `/`, `/usr`, `/usr/local`, `/usr/local/lib`, service-root,
and versioned-runtime chain must remain symlink-free, non-writable, and owned by
that same visible system-root identity.
A tool version change requires a new versioned installation
and an explicit administrator gate; obsolete versions are removed separately.
