# Android Phone CI/CD

The Android Phone pipeline separates untrusted device-free checks from trusted
APK builds. Neither workflow invokes ADB or changes a connected device.

## Pull-request and branch CI

`.github/workflows/android-tests.yml` runs the modular fast, contract, coverage,
mutation, Robolectric, and regression tiers on GitHub-hosted Ubuntu runners.
It has read-only permissions, does not persist checkout credentials, pins every
third-party action to an immutable commit, cancels superseded pull-request runs,
and retains reports for seven days.

## Trusted build

`.github/workflows/android-phone-build.yml` is manual-only and accepts only
`feature/android-phone-support` or immutable `android-phone-vX.Y.Z-alpha.N`
tags. It requires a runner with all of these labels:

```text
self-hosted, linux, x64, overte-android-phone-build
```

Treat this label as a security boundary. Use an isolated, preferably ephemeral
runner without unrelated credentials, signing material, or Android devices.
Never add a pull-request trigger to this workflow.

The workflow runs the complete device-free host tier, restores the published
checksum-verified dependency graph after the clean checkout, revalidates its
16 KiB sentinel, builds the ARM64 debug APK, and runs the existing complete APK
content/alignment gate. It additionally verifies the APK signature and records
the source revision, APK digest, signer-certificate digest, package, version,
SDK levels, debug state, ABI, and required 16 KiB page-size contract.

The trusted build uses a private Conan home inside its clean workspace. This is
required because Pico and Phone can otherwise share a Conan reference and
package ID despite different 4 KiB versus 16 KiB ELF alignment; Conan restore
correctly preserves an existing package and would leave the wrong variant in a
shared cache. The final dependency verifier still fails closed if any package
does not match the Phone sentinel.

Shared Pico runtime and host-tool preparation uses
`PHONE_SHARED_CONAN_HOME` (the normal user cache by default), while the
checksum-pinned Phone graph stays in the private `CONAN_HOME`. The Phone graph
is verified before compatibility staging and again by Gradle.

Only the small JUnit and JSON reports are retained for seven days. The APK is
not uploaded to general Actions artifact storage.

## Release-candidate stage

`.github/workflows/android-phone-release-candidate.yml` is the manual-only
second stage. It does not create a tag, GitHub Release, Play upload, attestation,
or any other publication. A GitHub-hosted preflight first validates the tag and
runs contracts. Only then can the protected `android-phone-release-candidate`
environment approve execution on the isolated
`overte-android-phone-release` runner.

The only accepted release identity is:

```text
android-phone-vM.m.p-alpha.N
```

Every numeric field is canonical decimal without leading zeroes; `N` starts at
one. Minor and patch are at most 999 and alpha is at most 99. `versionName` is
exactly `M.m.p-alpha.N`. `versionCode` is derived, never chosen independently:

```text
M * 100000000 + m * 100000 + p * 100 + N
```

The gate requires the tag to exist, resolve exactly to checked-out `HEAD`, be
newer than every matching repository tag, fit Android's signed 32-bit field,
and exceed the repository variable `ANDROID_PHONE_PUBLISHED_VERSION_CODE`.
That non-secret variable must be repository-scoped because the unprivileged
preflight runs before protected-environment approval. It is the fail-closed floor for builds already uploaded outside Git;
the release custodian must update it after every upload, including abandoned
Play tracks. A missing, empty, stale, or equal floor rejects the candidate.

The protected environment supplies four secrets only to the signing step:

```text
ANDROID_PHONE_UPLOAD_KEYSTORE_BASE64
ANDROID_PHONE_UPLOAD_KEYSTORE_PASSWORD
ANDROID_PHONE_UPLOAD_KEY_ALIAS
ANDROID_PHONE_UPLOAD_KEY_PASSWORD
```

It also supplies `ANDROID_PHONE_UPLOAD_CERT_SHA256` as a non-secret environment
variable. Store the lowercase SHA-256 of the upload certificate (colons are
also accepted). The build writes the decoded key under the worktree with mode
`0600`, uses it in one step, and removes it on exit. It then independently
requires one signer and the approved certificate digest.

The resulting 14-day Actions artifact is a locally inspectable draft candidate:
signed release APK, verified APK and version manifests, SHA-256 list,
CycloneDX 1.6 inventory of packaged ARM64 native libraries, source-archive
digest, and an unsigned in-toto/SLSA provenance statement. `published` remains
`false`. The same complete dependency, host, 16 KiB ELF/ZIP, APK contents,
permissions, metadata, signature, signer, and provenance gates apply.

Artifact Attestations are deliberately only prepared. After policy approval,
add a separately reviewed attestation step with `id-token: write` and
`attestations: write` scoped to that job, pin the official action by full commit
SHA, and attest the already verified APK digest. Do not broaden the current
workflow permissions merely to prepare for that later step.

See [ANDROID_PHONE_RELEASE_OPERATIONS.md](ANDROID_PHONE_RELEASE_OPERATIONS.md)
for tag protection, runner provisioning, key recovery, rollback, acceptance,
and post-push repository settings.

## Local checks

The CI/CD contracts require neither an Android SDK nor a device:

```bash
python3 android/tests/android-workflow-contract-test.py
python3 android/tests/phone-apk-provenance-test.py
python3 android/tests/phone-release-version-test.py
python3 android/tests/phone-release-metadata-test.py
```

Verify a locally built debug APK with the actual Android tools and package gate:

```bash
android/ci/verify-phone-apk.py \
  android/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk \
  --expect-debuggable 1 \
  --source-revision "$(git rev-parse HEAD)" \
  --output build/android-phone/apk-manifest.json
```

The verifier extracts large APK contents below
`android/build/apk-verification-tmp`, not a potentially memory-backed `/tmp`.
Set `PHONE_APK_VERIFY_TMPDIR` to select another build volume.
