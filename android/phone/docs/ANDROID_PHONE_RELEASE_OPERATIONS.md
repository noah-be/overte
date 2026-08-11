# Android Phone release operations

This runbook covers store-neutral release candidates only. No workflow in this
stage signs an APK, creates or publishes a GitHub Release, uploads to a store,
creates a tag, or installs an APK. The separate acceptance workflow is reserved
for a future signed channel artifact.

## Immutable tags and version authority

Release managers create `android-phone-vM.m.p-alpha.N` only after all required
branch checks pass. Before pushing a tag, run the gate against the intended
commit and current published floor. For example, `0.1.0-alpha.5` maps to code
`100005`:

```bash
android/phone/ci/verify-phone-release.py \
  --tag android-phone-v0.1.0-alpha.5 \
  --version-code 100005 \
  --published-code-floor 100004 \
  --source-revision "$(git rev-parse HEAD)"
```

The tag must already exist for this command. Treat a pushed tag as immutable:
never force it, retarget it, or reuse its name after a failed build. Fixes use a
new alpha number and therefore a new code. Configure a GitHub tag ruleset for
`refs/tags/android-phone-v*` that blocks updates and deletion, restricts tag
creation to the release-manager team, and bypasses only a documented emergency
administrator. Require signed tags when the organization has an enforceable
signing identity and recovery process; the local gate intentionally does not
pretend that a Git object signature replaces server-side immutability.

## Protected environments

Create `android-phone-release-candidate` with required reviewers who do not
author the candidate change. Disable administrator bypass if operationally
possible. This environment must contain no signing secrets. Set the non-secret
`ANDROID_PHONE_PUBLISHED_VERSION_CODE` as a repository variable so the preflight
can read it before environment approval, and update it after every publication
or store-reserved code. Restrict repository-settings changes to the release
administrators and audit every change to this floor.

Create a distinct `android-phone-emulator-acceptance` environment with required
reviewers. It holds no signing key. Dispatching its workflow requires the exact
RC run ID and attempt, tag, approved APK SHA-256, a checked emulator-test
approval box, and environment approval. The workflow verifies the ARM64
artifact digest and complete package gate, then builds and tests the same tagged
source with the dedicated x86_64 emulator graph. The unsigned ARM64 candidate
is never installed. Do not approve it merely because the RC build succeeded.

## Runner provisioning

The release runner must be isolated and preferably ephemeral, with labels
`self-hosted, linux, x64, overte-android-phone-release`. Provision JDK 17–21,
Node.js 18 or newer, Android SDK/NDK and Build Tools 36.0.0, CMake 3.31.6,
Ninja, Conan and the tools required by `build-phone.sh doctor`. Node.js is an
explicit runner prerequisite because the mandatory device-free JavaScript host
tests run before dependency restoration. The cached Qt host tools currently
require glibc 2.38 or newer; run the worker in an immutable, digest-pinned Ubuntu
24.04 (or equivalently compatible) image rather than directly on a Debian 12
host. Run that image as a non-root user, drop all Linux capabilities, enable
`no-new-privileges`, and expose neither the container-engine socket nor host
devices. Record and review every image-digest update.

Give the runner adequate non-tmpfs workspace for dependencies, packaging, and
APK verification. Allocate at least four logical CPU cores and 8 GiB RAM to the
release workload; the workflow caps CMake,
Pico/Ninja, and shader generation at four workers. Do not attach Android devices,
signing keys, general deployment credentials, persistent user Gradle properties, or a shared
Pico/Phone Conan home. Deny workflow execution from forks and pull-request
events at runner-group level. Restrict the runner group to this repository and
the protected RC workflow; use outbound network allowlisting where practical.
Destroy or scrub the workspace, process environment and Gradle state after every job.

For a repository-scoped runner where workflow-level runner groups are not
available, require approval for workflows from **all external contributors** in
the repository Actions settings. Install a root-owned copy of
`android/phone/ci/authorize-phone-release-runner.sh` outside the runner application
directory and set `ACTIONS_RUNNER_HOOK_JOB_STARTED` to its absolute path in the
runner `.env`. The hook independently permits only `noah-be/overte`, the manual
`Android Phone release candidate` workflow, and the named release custodian as
both actor and triggering actor. Keep the hook and its parent directory
non-writable by the runner service account. This local check is required even
when GitHub's fork approval policy is enabled: labels alone are not an access
control because pull-request code can request any repository runner label.

A standard GitHub-hosted Ubuntu runner is not currently a supported substitute:
its 14 GB workspace is smaller than the observed combined Phone Conan and
Gradle output before checkout and download staging are included. Re-evaluate a
hosted runner only after the dependency/package footprint is proven below its
ephemeral disk limit, or use an appropriately sized GitHub-hosted larger runner
when the repository is owned by an eligible organization. No signing-secret
argument remains for self-hosting; the current requirement is resource capacity
only.

The acceptance runner is separate and labeled
`self-hosted, linux, x64, overte-android-phone-emulator`. Give it the documented
x86_64/API-35 AVD, hardware acceleration, ADB, `gh`, Build Tools 36.0.0, Conan,
JDK 17--21, and no signing or publication credentials. Serialize it with the
workflow concurrency group and reset the emulator snapshot after every
approved run. Standard Android Emulator builds on an x86_64 host cannot execute
the ARM64-only release APK; the workflow therefore verifies that artifact
without installing it and runs the exact tagged source through the x86_64
instrumentation graph.

## Candidate review and later publication

Download the candidate artifact, run `sha256sum --check SHA256SUMS` from its
unpacked root (paths are basenames), and compare the APK, source and manifest
digests with the workflow summary and approved tag. Confirm that the APK
manifest says `signing_state: unsigned`. Review the SBOM, known vulnerabilities,
permissions, size change and host reports. Do not send this unsigned APK to an
emulator or users. F-Droid should build the tagged source through its reviewed
recipe; the candidate APK is a reference for reproducibility analysis.

When a signed distribution channel is authorized, keep signing and final
publication as distinct protected actions. A signed downstream candidate must
repeat the signer, APK-content and 16 KiB gates before any approved emulator
installation.

## Rollback and key recovery

Android version codes cannot be rolled back. To recover from a bad candidate,
revoke the candidate operationally, retain its manifests for audit, fix forward
under a new alpha tag/code, and never move the old tag. For an already
distributed build, halt publication, publish a higher-code corrected build, and
document the affected channel and digests.

The store-neutral stage has no key to recover. If a future channel adds an
Overte signing key, document its vault, two-person recovery, offline backup,
named custodians, rotation policy and certificate digest in that channel's
separate runbook. Never place such a key in the store-neutral environment.

## Recommended GitHub settings after push

Protect `android-phone` with pull requests, at least one
independent approval, dismissal of stale approvals, conversation resolution,
linear history, and no force pushes or deletion. Require branches to be current
before merge and require these checks from `Android tests`:

- `Fast host tests`
- `Architecture and security contracts`
- `JVM and native host coverage`
- `Complete device-free regression`

Require CODEOWNERS review for `.github/workflows/**`, `android/phone/ci/**`, Phone
signing/build files, dependency checksum manifests and these runbooks. Restrict
Actions to approved actions, require full-SHA pinning through policy, and set
the default workflow token to read-only. Apply the immutable tag ruleset above,
restrict both self-hosted runner groups to their named workflows/repository,
and audit environment approvals, secret changes, tag creation and runner-group
changes. The RC and emulator workflows are manual release controls and should
not be branch required checks because they intentionally require human approval.
