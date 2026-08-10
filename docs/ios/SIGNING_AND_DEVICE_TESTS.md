<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Signing and physical-device tests

Simulator builds are unsigned and need no Apple credentials. Physical-device
work is intentionally separate so pull-request code cannot access a developer
keychain or provisioning profile.

The `unsigned-device-sdk` CI job already compiles and inspects an `iphoneos`
bundle without Apple credentials. This catches SDK-only compiler, linker, plist,
architecture, and forbidden-dependency failures, but its app cannot be installed
on an iPad. Signing remains the boundary between autonomous cloud preparation
and a real-device test.

## External inputs

A device build needs:

- an Apple Developer team ID;
- a bundle identifier registered to that team;
- an Xcode-managed development certificate and provisioning profile; and
- an explicitly selected, trusted iPhone or iPad.

No certificate, profile, private key, keychain password, App Store Connect key,
or Apple account credential belongs in this repository or a command-line
argument recorded by CI.

After Xcode is signed into the intended account, configure a device build with:

```bash
./ios/build-ios.sh build \
  --platform device \
  --bundle-id org.example.overte \
  --development-team TEAMID
```

Automatic signing is only enabled when the team is supplied. The script never
installs the resulting app by itself.

## Acceptance execution

The required cases are machine-readable in
`ios/tests/device-acceptance.json`. Run every case on at least one supported
iPhone and one supported iPad. Record:

- source revision, Xcode build, SDK, OS, device model, and app bundle hash;
- pass, fail, or blocked status for each case;
- peak memory and thermal state for the endurance cases;
- screenshots or logs for visual and lifecycle failures; and
- the exact signing identity's team, never its private material.

A simulator result cannot satisfy a `deviceOnly` case. An App Store upload is a
separate externally approved release action and is not performed by the build
or acceptance scripts.

Each device result must follow `ios/tests/device-result.schema.json`. Once one
complete result exists for each form factor, validate the pair without network
access or Apple credentials:

```bash
python3 ios/tools/validate-device-results.py \
  ios/tests/device-acceptance.json iphone-result.json ipad-result.json
```

The validator requires the exact case order, immutable source and bundle
digests, evidence for every pass or failure, an explanation for every blocked
case, and repository-relative evidence paths. This prevents a partial or mixed
build run from being mistaken for device acceptance.

For an iPad-only, no-Mac workflow, continue with `IPAD_REMOTE_TESTING.md`.
