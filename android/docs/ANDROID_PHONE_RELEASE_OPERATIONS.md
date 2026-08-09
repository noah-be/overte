# Android Phone release operations

This runbook covers release candidates only. No workflow in this stage creates
or publishes a GitHub Release, uploads to Play, promotes a track, creates a tag,
or installs an APK unless a human explicitly dispatches and approves the
separate acceptance workflow.

## Immutable tags and version authority

Release managers create `android-phone-vM.m.p-alpha.N` only after all required
branch checks pass. Before pushing a tag, run the gate against the intended
commit and current published floor. For example, `0.1.0-alpha.5` maps to code
`100005`:

```bash
android/ci/verify-phone-release.py \
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

## Protected environments and secrets

Create `android-phone-release-candidate` with required reviewers who do not
author the candidate change. Disable administrator bypass if operationally
possible. Put the four upload-key values and approved certificate digest listed
in `ANDROID_PHONE_CI_CD.md` only in that environment, not at repository or
organization scope. Set `ANDROID_PHONE_UPLOAD_CERT_SHA256` as an environment
variable. Set the non-secret `ANDROID_PHONE_PUBLISHED_VERSION_CODE` as a
repository variable so the preflight can read it before environment approval,
and update it after every external upload. Restrict repository-settings changes
to the release administrators and audit every change to this floor.

Create a distinct `android-phone-emulator-acceptance` environment with required
reviewers. It holds no signing key. Dispatching its workflow requires the exact
RC run ID, tag, approved APK SHA-256, a checked installation approval box, and
environment approval. The workflow verifies the artifact digest and complete
package gate before its first ADB query, then opts into emulator use explicitly.
Do not approve it merely because the RC build succeeded.

## Runner provisioning

The release runner must be isolated and preferably ephemeral, with labels
`self-hosted, linux, x64, overte-android-phone-release`. Provision JDK 17–21,
Android SDK/NDK and Build Tools 36.0.0, CMake 3.31.6, Ninja, Conan and the tools
required by `build-phone.sh doctor`. Give it adequate non-tmpfs workspace for
dependencies, packaging, and APK verification. Do not attach Android devices,
general deployment credentials, persistent user Gradle properties, or a shared
Pico/Phone Conan home. Deny workflow execution from forks and pull-request
events at runner-group level. Restrict the runner group to this repository and
the protected RC workflow; use outbound network allowlisting where practical.
Destroy or scrub the workspace, process environment, Gradle state and decoded
keystore after every job.

The acceptance runner is separate and labeled
`self-hosted, linux, x64, overte-android-phone-emulator`. Give it one disposable
ARM64/API-26-or-newer touchscreen emulator, ADB, `gh`, Build Tools 36.0.0, and
no signing or publication credentials. Serialize it with the workflow
concurrency group and reset the emulator snapshot after every approved run.

## Candidate review and later publication

Download the candidate artifact, run `sha256sum --check SHA256SUMS` from its
unpacked root (paths are basenames), and compare the APK, source, signer and
manifest digests with the workflow summary and approved tag. Review the SBOM,
known vulnerabilities, permissions, size change, host reports and separately
approved emulator results. A later publication workflow must consume this exact
digest; it must not rebuild under the same tag and silently substitute bytes.

When real GitHub draft releases are authorized, create drafts only, retain
manual approval, use the verified artifact rather than rebuilding, and keep
final publication as a distinct protected action. Play promotion likewise
requires review of pre-launch results on 4 KiB and 16 KiB ARM64 devices.

## Rollback and key recovery

Android/Play version codes cannot be rolled back. To recover from a bad
candidate, revoke the candidate operationally, retain its manifests for audit,
fix forward under a new alpha tag/code, and never move the old tag. For an
already distributed build, halt promotion, use Play track controls as allowed,
publish a higher-code corrected build, and document affected digests and tracks.

Keep the upload key encrypted in an organizational secrets vault with two-person
recovery, offline backup, named custodians, rotation date, certificate digest,
and tested restore instructions. Do not back up passwords beside the key. If
the upload key is suspected compromised, disable RC approvals, remove the four
environment secrets, record the last trusted signer/APK digests, follow the Play
upload-key reset process, install the replacement only after independent digest
verification, and update `ANDROID_PHONE_UPLOAD_CERT_SHA256`. Loss of an upload
key must not lead to copying the Play app-signing key into CI.

## Recommended GitHub settings after push

Protect `feature/android-phone-support` with pull requests, at least one
independent approval, dismissal of stale approvals, conversation resolution,
linear history, and no force pushes or deletion. Require branches to be current
before merge and require these checks from `Android tests`:

- `Fast host tests`
- `Architecture and security contracts`
- `JVM and native host coverage`
- `Complete device-free regression`

Require CODEOWNERS review for `.github/workflows/**`, `android/ci/**`, Phone
signing/build files, dependency checksum manifests and these runbooks. Restrict
Actions to approved actions, require full-SHA pinning through policy, and set
the default workflow token to read-only. Apply the immutable tag ruleset above,
restrict both self-hosted runner groups to their named workflows/repository,
and audit environment approvals, secret changes, tag creation and runner-group
changes. The RC and emulator workflows are manual release controls and should
not be branch required checks because they intentionally require human approval.
