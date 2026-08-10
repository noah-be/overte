<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iPad testing without a local Mac

The prepared path is GitHub-hosted macOS for compilation and simulator tests,
followed by TestFlight for the physical iPad once release credentials are
explicitly approved. A Hackintosh is not part of the supported toolchain.

## What is autonomous now

The iOS workflow can run without Apple credentials and performs:

1. Linux host-contract and policy tests;
2. an unsigned arm64 build against the physical-device SDK;
3. unsigned iPhone and iPad simulator launches; and
4. simulator bundle packaging with a source revision and SHA-256 manifest.

The unsigned device-SDK output is compile evidence only. iPadOS will not install
it because it has no trusted signature or provisioning profile.

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
2. Build a signed archive from that revision in a protected macOS CI job.
3. Validate signing, entitlements, privacy metadata, bundle ID, and archive hash.
4. Upload to App Store Connect only after a separate manual approval.
5. Add the owner's Apple ID as an internal TestFlight tester and install on the
   iPad through the TestFlight app.
6. Execute `ios/tests/device-acceptance.json` and capture evidence using
   `ios/tests/device-result.schema.json`.
7. Validate the result offline with `ios/tools/validate-device-results.py`.

The acceptance contract currently requires both an iPhone and an iPad result.
An iPad-only run is still useful evidence, but it cannot mark the complete
device matrix as passed. Borrowing an iPhone or using an external tester remains
an explicit later coordination step.

## Stop conditions

The autonomous workflow must stop before enrolling in a paid program, creating
Apple identities, accepting legal agreements, generating or uploading signing
credentials, registering devices, inviting testers, or submitting a build for
review. Those actions change external account state and require the owner's
approval.
