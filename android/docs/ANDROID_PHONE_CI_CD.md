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
`android-phone` or immutable `android-phone-vX.Y.Z-alpha.N`
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

## Store-neutral release-candidate stage

`.github/workflows/android-phone-release-candidate.yml` is the manual-only
second stage. It produces an unsigned release APK and does not create a tag,
GitHub Release, store upload, attestation, signature, or any other publication.
A GitHub-hosted preflight first validates the tag and runs contracts. Only then
can the protected `android-phone-release-candidate` environment approve execution on the isolated
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
preflight runs before protected-environment approval. It is the fail-closed
floor for builds already distributed or reserved by any channel. The release
custodian must update it after every external publication or rejected store
submission. A missing, empty, stale, or equal floor rejects the candidate.

The protected environment contains no signing secrets. The build passes no
keystore properties and the verifier requires `apksigner` to report that the
candidate is unsigned. An accidentally or implicitly signed artifact fails the
gate. This unsigned APK is a reproducibility and store-handoff artifact; Android
cannot install it until a separately authorized channel signs it.

The resulting 14-day Actions artifact is a locally inspectable draft candidate:
unsigned release APK, verified APK and version manifests, SHA-256 list,
CycloneDX 1.6 inventory of packaged ARM64 native libraries, source-archive
digest, and an unsigned in-toto/SLSA provenance statement. `published` remains
`false`, and the release manifest records `store-neutral` and `unsigned`. The
same complete dependency, host, 16 KiB ELF/ZIP, APK contents, permissions,
metadata, unsigned-state, digest, and provenance gates apply.

## F-Droid-first distribution

The primary publication path is an F-Droid build recipe tied to the immutable
release tag. F-Droid builds from source in its own controlled environment and
signs the published APK with its repository key. The CI candidate supplies the
reviewable version/source mapping, dependency checks, SBOM, provenance and a
reference APK for reproducibility work; it is not submitted as a signed binary.

A future direct-download, private F-Droid repository, or Play channel must be a
separate protected workflow that consumes the already verified candidate digest
and applies that channel's signing policy. It must not silently rebuild or add
key material to this store-neutral workflow.

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
