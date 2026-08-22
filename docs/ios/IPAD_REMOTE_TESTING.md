<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iPad testing without a local Mac

The prepared path is GitHub-hosted macOS for compilation and simulator tests,
followed by Sideloadly signing/installation and privacy-minimal Fedora log
capture for a personal physical iPad. TestFlight remains an optional release
path, not a prerequisite for local acceptance. A Hackintosh is not part of the
supported toolchain.

## What is autonomous now

The iOS workflow can run without Apple credentials and performs:

1. Linux host-contract and policy tests;
2. an unsigned arm64 build against the physical-device SDK, packaged as a
   standard `Payload/*.app` IPA with a SHA-256 manifest;
3. unsigned iPhone and iPad simulator launches; and
4. simulator bundle packaging with a source revision and SHA-256 manifest.

The unsigned device IPA is compile and packaging evidence. iPadOS will not
install it until it is re-signed with a provisioning profile.

## Free personal sideloading

For development on one personal iPad, download the
`<build-number>-overte-ios-device-unsigned-<run-id>` workflow artifact and verify the SHA-256
value in its JSON manifest. On a trusted Windows or macOS computer, a tool such
as Sideloadly can apply a free Apple Personal Team signature and install the IPA
over USB. Keep this manual operation outside CI:

- never upload an Apple password, session, certificate, or provisioning profile
  to GitHub Actions or this repository;
- prefer a separate Apple Account when authenticating a third-party signing
  tool;
- expect free provisioning to expire after seven days, requiring refresh or
  reinstallation; and
- inspect the downloaded IPA digest and exact source revision before signing.

This route is suitable for iterative testing, not distribution. Sideloadly is a
third-party tool and is not part of the trusted Overte build pipeline.

### Full Client handoff gate

Do not use an `OverteIOSBootstrap` IPA for Universal Touch UI acceptance. The
complete downloaded artifact directory must contain the numbered integrated
client IPA, its same-stem manifest, and both `LATEST-OverteIOSClient` pointers.
Before copying anything to Sideloadly, run on Fedora:

```bash
python3 ios/tools/verify-sideload-handoff.py build-ios/artifacts
```

This fails closed for a bootstrap or simulator archive, an altered digest, a
non-arm64 device build, contradictory signing metadata, a stale pointer, or
private device fields. Record the printed IPA SHA-256 and compare it again after
the transfer into the Sideloadly environment. Signing changes the IPA bytes, so
the signed output must receive a new local checksum and must never replace the
unsigned source artifact or its manifest.

## Fedora log capture

Install the read-only device tools once from Fedora's repository:

```bash
sudo dnf install libimobiledevice-utils
python3 ios/tools/fedora-ipad-log.py doctor
```

The doctor prints only a connected-device count. It never prints a UDID, serial
number, device name, model, or Apple account. For capture, connect exactly one
trusted iPad, start the installed Full Client manually, and run:

```bash
python3 ios/tools/fedora-ipad-log.py capture \
  --output-dir ipad-evidence/session-01 \
  --bundle-id org.example.overte \
  --source-revision 0123456789abcdef0123456789abcdef01234567 \
  --ipa-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --duration-seconds 300
```

Only lines containing Overte or the exact bundle identifier are retained. The
tool discards oversized and unrelated lines, bounds the complete log to 2 MiB,
redacts device identifiers, UUIDs, email addresses, IP addresses, home paths,
model tokens, and user/device metadata, and writes private mode-0600 evidence.
The raw syslog is never stored. Review the sanitized output before attaching it
to an acceptance result.

Create the iPad-only result worksheet after the final IPA and iPadOS version are
known:

```bash
python3 ios/tools/prepare-ipad-result.py \
  --output ipad-evidence/ipad-result.json \
  --source-revision REVISION \
  --ipa-sha256 CANDIDATE_DIGEST \
  --xcode 'Xcode 26.6 (17F113)' --sdk 26.5 --os-version 26.0
```

Every case starts as `blocked`; replace the outcome, notes, and evidence paths
only after actually executing it. The result deliberately records the form
factor and OS version but no model, serial number, UDID, device name, or user.

## External gate for the first iPad build

Before adding a signed workflow, provide and approve all of the following:

- active Apple Developer Program and App Store Connect access;
- final reverse-DNS bundle identifier and Apple team ID;
- an App Store Connect app record owned by that team;
- a distribution certificate and provisioning profile, or an approved managed
  signing mechanism; and
- an App Store Connect API key restricted to the minimum required role.

Store private material only as protected CI environment secrets. Require manual
workflow dispatch and environment approval, pin every third-party action by
commit, disable credential persistence, and never expose secrets to pull-request
jobs. Do not place a certificate, profile, private key, or API key in Git.

## First physical-device sequence

1. Freeze the exact source revision that passed all credential-free CI gates.
2. Build and publish the unsigned integrated Full Client from the protected
   GitHub macOS workflow.
3. Verify its manifest and hash with `verify-sideload-handoff.py`.
4. Sign and install that exact IPA through the separately authorized Sideloadly
   environment; record a new local checksum for the signed derivative.
5. Capture privacy-filtered Fedora logs while executing
   `ios/tests/device-acceptance.json` and record evidence using
   `ios/tests/device-result.schema.json`.
6. Validate the result offline with `ios/tools/validate-device-results.py` once
   every required form factor is available.

The release acceptance contract currently requires both an iPhone and an iPad
result. An iPad-only run is valid local evidence for this validation but cannot
mark the complete release device matrix as passed. The agreed single iPhone
simulator smoke does not substitute for a physical iPhone result.

## Stop conditions

The autonomous workflow must stop before enrolling in a paid program, creating
Apple identities, accepting legal agreements, generating or uploading signing
credentials, registering devices, inviting testers, or submitting a build for
review. Those actions change external account state and require the owner's
approval.
