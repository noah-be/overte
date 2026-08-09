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

Only the small JUnit and JSON reports are retained for seven days. The APK is
not uploaded to general Actions artifact storage.

## Release boundary

This stage verifies debug builds but does not publish them. Release automation
should be added only after the upload-key owner, protected GitHub environment,
version-code authority, and recovery procedure are agreed. A future job should:

1. build only an existing immutable Phone release tag;
2. require explicit `VERSION_CODE` and `RELEASE_NUMBER` values that match the
   tag and exceed the latest published code;
3. obtain signing credentials only after protected-environment approval;
4. rebuild and run the same 16 KiB, contents, permission, and signature gates;
5. create a draft release and publish only after human review;
6. attach the APK digest, signer digest, source revision, and test report.

## Local checks

The CI/CD contracts require neither an Android SDK nor a device:

```bash
python3 android/tests/android-workflow-contract-test.py
python3 android/tests/phone-apk-provenance-test.py
```

Verify a locally built debug APK with the actual Android tools and package gate:

```bash
android/ci/verify-phone-apk.py \
  android/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk \
  --expect-debuggable 1 \
  --source-revision "$(git rev-parse HEAD)" \
  --output build/android-phone/apk-manifest.json
```
