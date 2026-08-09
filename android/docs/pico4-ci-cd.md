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

Every trusted build restores the dependency bundle after checkout because the
checkout's clean operation removes generated runtime files inside the worktree.
The restore verifies the committed SHA-256 manifest before changing the
Conan/runtime cache. This deliberately favors reproducibility over avoiding the
roughly 1.1 GB download in a manually triggered build.

The build runs all device-free tests before compiling, builds the debug APK,
and rejects output with an unexpected package, SDK contract, ABI, native
library set, ZIP structure, or signature. Its JSON manifest records the exact
Git revision and APK SHA-256 digest. Only that small manifest and the JUnit
report are uploaded to Actions storage for seven days. The roughly 550 MB APK
is deliberately not uploaded as an ordinary workflow artifact.

## Release-candidate stage

`.github/workflows/pico4-release-candidate.yml` is the manual-only second
stage. Dispatch it from an existing tag named
`pico4-vMAJOR.MINOR.PATCH-rc.N`, for example `pico4-v1.4.0-rc.2`. Mutable
branches, preview tags, final-version tags, tag/ref mismatches and RC zero are
rejected. Minor and patch are limited to 0..99 and RC to 1..99. The tag derives
both Android values without an independent input:

```text
versionName = MAJOR.MINOR.PATCH-rc.N
versionCode = MAJOR*10000000 + MINOR*100000 + PATCH*1000 + N
```

The APK verifier compares both values, the exact source commit and the release
certificate SHA-256 fingerprint after signing. The workflow produces canonical
JSON provenance, a dependency-bundle CycloneDX SBOM and sorted SHA-256 manifest.
This SBOM is an initial supply-chain inventory, not a claim that every native
or Java transitive component has been enumerated. `SHA256SUMS` is also the
subject list intended for a later GitHub artifact-attestation step; attestation
is deliberately not enabled until organization policy and OIDC trust are
configured.

The only network-side result is a **draft** GitHub release with verified files.
The workflow contains no publish operation. Re-running for a tag with an
existing release fails instead of replacing assets.

### Protected environment and secrets

Create an environment named `pico4-release-candidate`, require selected release
maintainers as reviewers, prevent self-review where supported, restrict it to
protected Pico RC tags, and store only these environment secrets:

- `PICO_RELEASE_KEYSTORE_BASE64`: base64 of the dedicated Android keystore;
- `PICO_RELEASE_STORE_PASSWORD`, `PICO_RELEASE_KEY_ALIAS`, and
  `PICO_RELEASE_KEY_PASSWORD`;
- `PICO_RELEASE_CERT_SHA256`: lowercase 64-hex certificate fingerprint.

Do not create repository-level copies. The temporary keystore is mode-restricted
and removed in an always-running cleanup step. Rotate the key through a reviewed
environment change and update the expected fingerprint at the same time.

### Runner provisioning

The release runner requires labels `self-hosted, linux, x64,
overte-android-release`, the toolchain from `PICO4_BUILD.md`, `base64`, and the
GitHub CLI authenticated only through the job token. It must be isolated from
pull-request runners and devices, preferably ephemeral, have no ambient cloud
or repository credentials, and start from an empty build directory. Pin the
runner image/tool versions administratively and retain its inventory with each
candidate. Never assign `overte-android-release` to a general build host.

### Later device-acceptance handoff

Device acceptance is a separate, approval-gated stage that consumes the APK
digest from `SHA256SUMS`, verifies it before any ADB action, takes the shared
device lock, and uploads a signed test report referring to tag, commit and APK
digest. It must never rebuild or publish. No release workflow here invokes ADB.

### Required checks and repository administration

After pushing, protect `feature/pico4-support` and Pico CI branches with the
`Pico 4 device-free CI / project-tests` check, required review, conversation
resolution, and blocked force-push/deletion. Configure a tag ruleset for
`pico4-v*-rc.*` that restricts creation to release maintainers and blocks update
and deletion. GitHub cannot require a workflow check before creating the tag;
therefore create it only from a reviewed commit whose device-free check passed.
The environment approval and `Pico 4 release candidate / release-candidate`
job are release gates, not merge checks. Do not make the manual release job a
required branch check because ordinary pull requests cannot trigger it.

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
