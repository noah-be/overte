# Pico 4 CI/CD

The Pico pipeline is intentionally split into an untrusted, device-free check
and a trusted build. Neither workflow connects to a headset or invokes ADB.

## Device-free pull-request CI

`.github/workflows/project-tests.yml` runs on GitHub-hosted Ubuntu runners for
pull requests and relevant branch pushes. It executes the dependency-light
project suite and retains only its JUnit report for seven days. The workflow
has read-only repository permissions, does not persist checkout credentials,
cancels superseded runs, and pins every third-party action to an immutable
commit.

## Trusted Pico build

`.github/workflows/pico4-build.yml` is manual-only. It executes repository code
on a runner carrying all of these labels:

```text
self-hosted, linux, x64, overte-android-build
```

Treat that label as a security boundary. Assign it only to an isolated runner
dedicated to trusted Overte Android builds. Do not add a pull-request trigger:
unreviewed code must never execute on this host. Prefer an ephemeral runner;
otherwise remove the checkout and build directories after each job and do not
place unrelated credentials, signing material, or device access on the host.
The workflow also rejects every source ref except `feature/pico4-support` and
immutable `pico4-preview-N` tags.

Provision the runner by following `android/PICO4_BUILD.md`, then verify it from
the repository root:

```bash
android/build-pico.sh doctor
android/build-pico.sh deps --download
android/build-pico.sh prepare
```

The dependency restore verifies the committed SHA-256 manifest before changing
the Conan/runtime cache. Normal builds can reuse the provisioned dependencies.
Select `refresh_dependencies` when the bundle version changes or when a shared
cache contains an incompatible host package.

The build runs all device-free tests before compiling, builds the debug APK,
and rejects output with an unexpected package, SDK contract, ABI, native
library set, ZIP structure, or signature. Its JSON manifest records the exact
Git revision and APK SHA-256 digest. Only that small manifest and the JUnit
report are uploaded to Actions storage for seven days. The roughly 550 MB APK
is deliberately not uploaded as an ordinary workflow artifact.

## Release automation boundary

The trusted workflow is build verification, not unattended publication. A
future release job should be introduced only after release signing and version
ownership are explicit. It should:

1. accept an existing immutable Pico release tag, never an arbitrary mutable
   branch or a local APK;
2. rebuild that tag on an isolated trusted runner and run the same verifier;
3. require a protected GitHub environment approval before receiving narrowly
   scoped `contents: write` permission;
4. create a draft release first, attach the verified APK directly to the draft,
   and publish only after human review;
5. publish the source revision, APK digest, signer certificate digest, and test
   result beside the asset.

Android Phone CI should reuse the same separation and contract-testing pattern
on its own product branch. It must define its own package, ABI, native-library,
version, signing, and artifact-size contracts rather than importing Pico values.

## Local contract checks

Run the workflow and APK-verifier regressions without Actions or an Android
device:

```bash
python3 tests/workflow-contract-test.py
python3 android/tests/pico-apk-verifier-test.py
```

These checks prevent permission expansion, mutable action references,
credential persistence, untrusted self-hosted execution, accidental large APK
artifact uploads, and weakening of the Pico APK identity checks.
