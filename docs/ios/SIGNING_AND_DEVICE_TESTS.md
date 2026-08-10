<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Signing and physical-device tests

Simulator builds are unsigned and need no Apple credentials. Physical-device
work is intentionally separate so pull-request code cannot access a developer
keychain or provisioning profile.

The `unsigned-device-sdk` CI job compiles and inspects an `iphoneos` bundle
without Apple credentials, then packages it as an unsigned IPA with a SHA-256
manifest. This catches SDK-only compiler, linker, plist, architecture,
forbidden-dependency, and IPA-layout failures. The IPA still cannot be installed
on an iPad until a trusted local tool applies a personal or paid-team signature.
Signing remains the boundary between autonomous cloud preparation and a
real-device test.

## Experimental integrated-client artifact

After the explicit full-client graph has configured and target `Overte` has
built successfully, package that existing bundle without rebuilding the
bootstrap application:

```bash
cmake --build build-ios/device --config Debug --target Overte
OVERTE_IOS_ARTIFACT_SEQUENCE=123 \
  ios/build-ios.sh package-client --platform device --configuration Debug
```

`package-client` rejects zero or missing sequence numbers, missing executables,
Info.plists, and privacy manifests. It never silently falls back to the
bootstrap bundle. Device output is named like
`0123-OverteIOSClient-Debug-device-unsigned.ipa`; the existing bootstrap names
and numbering remain unchanged.

Each package has a same-stem JSON manifest plus
`LATEST-OverteIOSClient.json` and `LATEST-OverteIOSClient.txt`. The JSON records
the exact artifact name, source revision, SHA-256, platform, signing state, and
a Windows `certutil` verification command. GitHub Actions uploads all four files
in one numbered artifact. Download or copy that complete artifact into the
VirtualBox shared folder; the Windows VM should select the filename from
`LATEST-OverteIOSClient.txt` and verify it against the JSON digest before
passing an unsigned IPA to the separately authorized signing tool.

For an unsigned device artifact, `package-client` rejects a stale
`_CodeSignature` directory or embedded provisioning profile. Its JSON records
that no profile, application identifier, or `get-task-allow` value was observed;
Sideloadly remains responsible for applying its own authorized signature.

If a development team is explicitly selected, packaging additionally requires
a valid `codesign --verify --deep --strict` result and an
`embedded.mobileprovision`. The signature and decoded profile must agree on the
team, exact `TEAMID.bundle.identifier`, and `get-task-allow` value. The latter is
reported, not forced: development and distribution profiles legitimately use
different values. Certificates, profiles, and private keys are never copied to
artifact metadata.

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
