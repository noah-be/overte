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
Info.plists, and privacy manifests. It also parses the finished app metadata
before packaging: the requested `CFBundleIdentifier`, numeric
`CFBundleShortVersionString`, numeric `CFBundleVersion`, target platform and
Full Client URL schemes must all be concrete and installer-valid. Unresolved
or missing Xcode substitutions therefore fail before an IPA can be uploaded.
It never silently falls back to the bootstrap bundle. Device output is named like
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

Before copying the downloaded artifact directory into the VirtualBox shared
folder, verify the current pointer, number, bytes, and signing state offline:

```bash
python3 ios/tools/verify-windows-handoff.py build-ios/artifacts
```

Copy the complete directory entry selected by `LATEST-OverteIOSClient.txt`
together with both `LATEST` files and its same-stem JSON. The verifier rejects
a stale pointer, mismatched leading build number, missing file, SHA mismatch,
unsafe relative path, or contradictory signing flags. It prints whether the
IPA still requires Sideloadly signing; it does not start or modify the VM and
does not publish the artifact.

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

## Read-only readiness summary

After artifact handoff verification, optionally combine it with the entity-gate
ZIP without changing either input:

```bash
python3 ios/tools/check-release-readiness.py build-ios/artifacts
python3 ios/tools/check-release-readiness.py build-ios/artifacts \
  --entity-evidence ipad-entity-evidence.zip
```

The first command can report `build-ready` after checking the numbered manifest,
SHA, Windows handoff pointers, embedded Info.plist, privacy allowlist, iPhone/iPad
family and minimum-OS metadata. It never calls that state device acceptance. The
second reports `device-accepted` only when the six-gate iPad evidence is accepted
and bound to the exact source revision and artifact SHA. Invalid supplied
evidence blocks readiness rather than being silently ignored. The aggregator is
read-only and performs no upload, signing, VM, or device operation.

The opt-in integrated GitHub workflow runs this same no-evidence form after
packaging and before artifact upload. It fails unless the report is exactly
`build-ready` with `deviceAccepted: false`, then uploads a numbered
`*-device-unsigned-readiness.json` beside the IPA and transfer metadata. CI does
not manufacture or infer physical-device acceptance.

## Failure diagnostics

The integrated Xcode build routes C, C++, Objective-C and Objective-C++
compilations through a pinned `sccache` client. It writes content-addressed
compiler results into a bounded 512 MiB workspace cache
as compilation succeeds. Immediately after either a successful Xcode build or
a normal compiler/link failure, CI uploads that checkpoint under a new immutable
generation. A later source-only fix can then reuse unchanged translation units.
The cache namespace is bound to the exact Xcode, iPhoneOS SDK,
CMake, Qt host/target, Conan, V8, MoltenVK and configure-policy identities; the
source revision is deliberately not part of that namespace because source,
headers and compiler flags are already part of every content key. CI fails if
Xcode bypasses the launcher or if the compiler cache reports write
errors.

The pinned sccache Xcode integration requires response files, Clang modules and
the index store to be disabled. CI checks all four effective Xcode build
settings and compiles a small Xcode target through the launcher before starting
the full client. A missing launcher invocation therefore fails in seconds
instead of being discovered after a long build. The repository contains no
Objective-C `@import` consumer.

While configure, dependency resolution, compilation, checkpoint creation and
packaging run, a secret-safe supervisor reports process-tree activity, active
CPU time, RAM, swap, disk space and bounded directory growth every 30 seconds.
It never prints process arguments or environment variables. Each individual
Xcode/V8 compiler invocation additionally runs through a CPU-aware watchdog
before sccache. A genuinely inactive compiler is diagnosed and terminated
fail-closed; long CPU-active translation units are not mistaken for hangs. The
original child exit status is preserved, and complete private phase output is
sanitized before a failure artifact is uploaded.

Only the newest generation across all full-client compiler namespaces for the
matching branch and runner architecture are retained, so obsolete toolchain
namespaces cannot accumulate and displace the separately validated Qt, V8,
MoltenVK and Conan checkpoints. A hard runner termination can still prevent the final cache
upload; ordinary compile and link failures do not. Cache-upload or pruning
trouble is reported without replacing the original compiler diagnostic.

Validated V8 and Conan outputs also receive provenance-bound 30-day workflow
artifacts, so repository cache eviction cannot force an unnecessary full
rebuild. A failed Conan resolution saves its isolated partial package home under
a non-durable recovery key; only an integrity-checked compact graph becomes a
durable artifact.

The generated Xcode project, `CMakeCache.txt`, products, bundles, signing data,
raw diagnostics and the complete workspace are not cached. They are regenerated
and revalidated on every runner, avoiding stale project graphs and embedded
absolute paths. Linking and packaging therefore still run normally, while the
expensive unchanged compilation work is recoverable.

On configure, Xcode build, or packaging failure, integrated CI retains raw logs
only inside the ephemeral runner workspace. Before upload it keeps at most the
last 2 MiB per log and redacts credential-shaped assignments, authenticated
URLs, and private-key blocks. Only files in `ci-upload-diagnostics` are uploaded;
`CMakeCache.txt`, raw logs, credentials, profiles, and keychains are excluded.
The failure artifact name begins with the workflow run number and expires after
seven days. Redaction is defense in depth: build commands must still never print
credentials in the first place.

For an iPad-only, no-Mac workflow, continue with `IPAD_REMOTE_TESTING.md`.
