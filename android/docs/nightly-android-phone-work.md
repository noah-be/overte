# Android phone nightly work

This file records the cumulative Android phone work based on
`origin/feature/android-phone-support`. Most validation is device-free; any
real-device test is identified explicitly and never implied by a host check.

## 80 — Label privacy-reduced ADB phase failures

- Branch: `nightly/android-phone-80-adb-phase-errors`
- Commit: `Report phone smoke ADB phase failures` (this task's commit)
- Change: Route install, force-stop, Activity starts, deep-link delivery, Home,
  and Back through a checked phase wrapper. Raw ADB detail remains suppressed,
  while failures now identify the exact safe phase and cannot continue.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**; a launcher-start
    error with a synthetic serial on stderr becomes only `launcher start failed`
    and never records launch success.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 257/257 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 257/257 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Detailed transport diagnosis intentionally remains a separate,
  local operator action after the safe phase has been identified.
- Real-device validation still required: Interrupt one disposable current-APK
  lifecycle phase and confirm the generic phase name with no identifier leakage.

## 79 — Keep ADB transport errors identifier-free

- Branch: `nightly/android-phone-79-private-adb-errors`
- Commit: `Minimize phone smoke ADB error output` (this task's commit)
- Change: Suppress raw stderr for every selected-device ADB command and replace
  installation detail with a generic checked failure. A disconnect or install
  error can no longer place a serial or local APK path in shared console logs.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**; a failed install
    emits a synthetic serial/path on raw stderr, which is absent from captured
    smoke output while the generic error remains.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 255/255 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 255/255 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Detailed ADB diagnosis now requires an intentional separate local
  command outside shared logs; smoke output preserves phase and exit status.
- Real-device validation still required: Disconnect/revoke ADB during a
  disposable current-APK run and confirm no serial/path appears in output.

## 78 — Complete local APK validation before ADB

- Branch: `nightly/android-phone-78-local-preflight-order`
- Commit: `Validate phone APK before device selection` (this task's commit)
- Change: Move device selection after every local artifact check: file/hash,
  identity, SDKs, permissions, debug mode, contents, ELF, zipalign, and padding.
  Invalid input now causes zero ADB commands, including read-only property calls.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**; foreign/stale/
    extra-permission/mode/package-gate failures each leave the ADB command log
    completely empty.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 253/253 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 253/253 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Local preflight can take longer before reporting device
  availability because native libraries are inspected first; no device state is
  touched during that time.
- Real-device validation still required: Run the current-APK smoke and confirm
  the first ADB interaction occurs only after local preflight completes.

## 77 — Gate complete APK packaging before device changes

- Branch: `nightly/android-phone-77-apk-package-preflight`
- Commit: `Run phone package gate before device install` (this task's commit)
- Change: Make the combined Phone APK contents, native ELF, 16-KiB zipalign,
  and padding checker a mandatory smoke-test preflight before report creation or
  ADB installation. External artifacts no longer rely on having come through a
  correctly configured Gradle task.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including a
    package-gate failure rejected before any install command.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 252/252 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 252/252 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Device smoke now requires Build-Tools 36 `zipalign`, Python, and
  ELF inspection tools, intentionally matching the documented host toolchain.
- Real-device validation still required: Produce a current APK that passes the
  package gate, record its digest, and run the full unattended smoke.

## 76 — Distinguish debug and release device tests

- Branch: `nightly/android-phone-76-apk-debug-contract`
- Commit: `Record phone APK debug mode in device smoke` (this task's commit)
- Change: Read and strictly validate the final APK's debuggable flag, record it
  only as `apk_debuggable=0/1`, and allow unattended callers to require the
  expected mode with `PHONE_EXPECT_DEBUGGABLE`. Mode mismatch aborts before ADB.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, recording debug
    mode and rejecting a debug APK when release mode is required, before install.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 250/250 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 250/250 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Omitting `PHONE_EXPECT_DEBUGGABLE` accepts either mode but records
  it unambiguously; release automation should always set it to `0`.
- Real-device validation still required: Run both current debug and signed
  release APKs with the corresponding expected mode and retain their digests.

## 75 — Gate permissions in the actual APK

- Branch: `nightly/android-phone-75-apk-permission-preflight`
- Commit: `Verify phone APK permissions before install` (this task's commit)
- Change: Read, normalize, and exactly compare permissions from the final APK
  against the five required Phone permissions before ADB. Unexpected transitive
  manifest contributions and missing required capabilities both fail closed.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including an APK
    with unexpected camera permission rejected before installation.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 248/248 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 248/248 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Future intentional permission changes require coordinated source,
  data-protection, package-preflight, documentation, and device review.
- Real-device validation still required: Run with a current built APK and
  confirm its merged permission allowlist passes before installation.

## 74 — Reject stale Phone APK SDK metadata

- Branch: `nightly/android-phone-74-apk-sdk-preflight`
- Commit: `Verify phone APK SDK metadata before install` (this task's commit)
- Change: Extend local `apkanalyzer` preflight to require the current Phone
  artifact's exact minSdk 26 and targetSdk 36 before ADB. An old APK sharing the
  package ID can no longer alter the device before being identified as stale.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including a
    targetSdk 35 APK rejected before any install command.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 246/246 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 246/246 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Intentional future SDK changes must update Gradle, manifest
  contracts, and this device preflight together.
- Real-device validation still required: Run the smoke with a current built APK;
  do not install an older APK merely to test the negative fixture already mocked.

## 73 — Reject foreign APKs before device installation

- Branch: `nightly/android-phone-73-apk-identity-preflight`
- Commit: `Verify phone APK identity before install` (this task's commit)
- Change: Resolve the SDK `apkanalyzer`, read the local artifact's application
  ID, and require exactly `org.overte.phone` before creating reports or issuing
  ADB install. A mistaken foreign APK can no longer alter the phone before the
  post-install digest check notices a mismatch.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including an
    unrelated application ID rejected with no install command.
  - Local tool capability: **passed**, SDK `apkanalyzer` is available.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 244/244 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 244/244 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: `apkanalyzer` requires Android command-line tools and a working
  Java runtime; missing analysis capability intentionally blocks device changes.
- Real-device validation still required: Run the current-APK smoke and confirm
  identity preflight precedes installation; no foreign APK should be installed
  merely to exercise the negative path.

## 72 — Enforce the Phone runtime device requirements

- Branch: `nightly/android-phone-72-device-runtime-contract`
- Commit: `Check phone smoke runtime requirements` (this task's commit)
- Change: Complete the pre-install target contract with numeric Android API 26+
  and OpenGL ES 3.2+ checks, matching Gradle and manifest requirements that a
  direct ADB install may not prefilter. Invalid/missing properties fail closed.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including API 25
    rejection before installation.
  - Anonymous locked device runtime probe: **passed**,
    `phone_runtime_contract=1`; no values or identifier were logged.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 241/241 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 241/241 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Vendor builds with malformed standard numeric properties fail
  closed even if their hardware might otherwise work.
- Real-device validation still required: Exercise rendering on representative
  minimum API/ES hardware; the prepared phone's positive preflight is complete.

## 71 — Restrict smoke tests to supported physical phones

- Branch: `nightly/android-phone-71-device-target-contract`
- Commit: `Validate phone smoke device capabilities` (this task's commit)
- Change: Device selection now rejects qemu/emulators, VR, watches, TVs,
  automotive targets, missing touchscreens, and ABI lists without ARM64. Both
  implicit single-device selection and explicit `ANDROID_SERIAL` enforce the
  same APK-supported physical Phone contract before installation.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including a
    qemu target rejected before any install command.
  - Anonymous locked device capability probe: **passed**,
    `supported_physical_phone_contract=1`; no property or identifier was logged.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 239/239 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 239/239 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Unusual physical Android devices that omit standard feature or
  ABI properties fail closed and require local investigation.
- Real-device validation still required: Separately verify an emulator/TV
  target is refused without installation; the prepared phone's positive
  capability preflight is complete.

## 70 — Avoid benign 16-KiB log false positives

- Branch: `nightly/android-phone-70-page-size-markers`
- Commit: `Tighten phone page-size log markers` (this task's commit)
- Change: Stop treating every generic `16 KB`/`16 KiB` app log line as an
  incompatibility. Explicit page-size mismatch forms still count; otherwise the
  size token must accompany error, failure, incompatibility, invalidity,
  unsupported, or misalignment context.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**; a benign
    verification message records zero, while an incompatible linker-alignment
    message records one and returns the diagnostic failure status 2.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 236/236 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 236/236 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Unseen OEM linker wording may need a reviewed explicit marker;
  aggregate real-device logs should be correlated with the static ELF gate.
- Real-device validation still required: Run a current 16-KiB APK and confirm
  normal compatibility telemetry stays at zero; use an isolated known-bad APK
  to confirm its linker wording is detected without persisting raw logs.

## 69 — Validate Android exit-info structure

- Branch: `nightly/android-phone-69-exit-info-contract`
- Commit: `Validate phone exit diagnostics structure` (this task's commit)
- Change: Require the stable Android `PROCESS EXIT INFO` header before parsing
  crash counts and reject a final count lower than the launch baseline. An
  unknown dumpsys command, output-format drift, or mid-test reset can no longer
  masquerade as zero package crashes.
- Tests:
  - Anonymous locked device structure probe: **passed**,
    `exit_info_header=1 structured_fields=1`; no raw output was retained.
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed** with the
    structural response contract and existing transport-failure fixture.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 235/235 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 235/235 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: OEMs that remove the standard header will now fail explicitly;
  their output must be reviewed before any parser extension.
- Real-device validation still required: Run the full current-APK smoke and
  confirm before/after exit-info remains monotonic through all lifecycle phases.

## 68 — Fail closed when device diagnostics are unavailable

- Branch: `nightly/android-phone-68-device-diagnostic-failures`
- Commit: `Propagate phone device diagnostic failures` (this task's commit)
- Change: Replace status-masking logcat process substitution with checked
  command substitution and stop ignoring `dumpsys activity exit-info` transport
  failures. The smoke cannot report zero crashes when either diagnostic source
  was unavailable or returned malformed counters.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including new
    logcat and exit-info failure fixtures that must abort before success fields.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 233/233 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 233/233 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Vendor builds that do not expose package exit info will now fail
  the smoke explicitly instead of producing an unverifiable clean result.
- Real-device validation still required: Run current-APK smoke normally, then
  isolate ADB mid-diagnostic in a disposable test and confirm a nonzero result.

## 67 — Bound device log diagnostics to the test window

- Branch: `nightly/android-phone-67-logcat-delta`
- Commit: `Bound phone smoke logcat to launch time` (this task's commit)
- Change: Capture a validated millisecond epoch from the device immediately
  before launch and pass it to `logcat -T` together with the tested PID. Crash
  and 16-KiB markers from an older process that reused the PID can no longer
  create false failures, while launch-time linker markers remain covered.
- Tests:
  - Anonymous locked device capability probe: **passed**,
    `device_epoch_cursor_supported=1`; no identifier or logs were read.
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, exercising the
    cursor command and time-bounded logcat invocation.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 231/231 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 231/231 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Vendor logcat implementations must accept the documented epoch
  `-T` form; lack of cursor support intentionally fails before launch.
- Real-device validation still required: Run the full smoke with a current APK
  and confirm launch-time crash/page-size markers are counted while older
  entries for a recycled PID are excluded.

## 66 — Keep device-test console output path-private

- Branch: `nightly/android-phone-66-private-device-output`
- Commit: `Hide private paths in phone device output` (this task's commit)
- Change: Remove absolute report directories from all device-smoke success and
  lifecycle failure messages. Output now says only `temporary` or
  `caller-provided`; callers needing a known retained location select it via
  `PHONE_TEST_REPORT` without exposing it to shared logs.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, asserting the
    private fixture root is absent from success, digest-mismatch, PID-restart,
    and sticky-foreground output.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 230/230 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 230/230 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Automatically created temporary report paths are intentionally
  not printed; select `PHONE_TEST_REPORT` before running when retention matters.
- Real-device validation still required: Run a current-APK smoke from a worktree
  under a non-public path and confirm no absolute path appears in captured output.

## 65 — Keep shared doctor output path-private

- Branch: `nightly/android-phone-65-private-doctor-status`
- Commit: `Minimize phone doctor dependency diagnostics` (this task's commit)
- Change: Suppress detailed verifier stdout/stderr inside doctor and expose only
  aggregate `[READY]`/`[STALE]` status. This prevents absolute Conan/home paths
  from entering shared diagnostic logs; direct verifier runs retain detail for
  deliberate local troubleshooting.
- Tests:
  - `android/tests/phone-doctor-output-test.sh`: **passed**, with a synthetic
    private path that must not escape the verifier subprocess.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 229/229 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 229/229 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Shared doctor logs trade detailed stale-file diagnosis for
  privacy; the documented direct verifier provides those details on demand.
- Real-device validation still required: None for diagnostic privacy.

## 64 — Verify dependency contents in doctor

- Branch: `nightly/android-phone-64-doctor-content-verification`
- Commit: `Verify phone dependencies before doctor readiness` (this task's commit)
- Change: A present marker no longer earns `[READY]` by existence alone. Doctor
  runs the full read-only content hash, symlink boundary, and ELF-alignment
  verifier; mismatches report `[STALE]` and fail, while absent graphs remain the
  normal non-failing `[SETUP]` state.
- Tests:
  - `android/tests/phone-doctor-output-test.sh`: **passed**, covering setup,
    content-verified ready, stale, and shared-checker failure states.
  - `./android/build-phone.sh doctor`: **passed**, expected `[SETUP]` locally.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 228/228 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 228/228 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Doctor takes longer on a prepared graph because it hashes and
  checks every relevant native dependency; this is intentional verification.
- Real-device validation still required: None for dependency diagnosis.

## 63 — Report Phone dependency readiness in doctor

- Branch: `nightly/android-phone-63-doctor-dependency-status`
- Commit: `Report phone dependency readiness separately` (this task's commit)
- Change: Keep the shared toolchain diagnosis, then explicitly report `[SETUP]`
  or `[READY]` for the dedicated atomic 16-KiB dependency marker. A green host
  toolchain can no longer be mistaken for an immediately buildable Phone graph.
- Tests:
  - `android/tests/phone-doctor-output-test.sh`: **passed**, covering missing and
    present marker states plus preservation of shared checker failures.
  - `./android/build-phone.sh doctor`: **passed**, reports `[SETUP]` in this
    worktree because dedicated dependencies are absent.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 227/227 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 227/227 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Marker presence is a fast status hint; Gradle's content-bound
  verifier remains authoritative and can still reject a stale marker.
- Real-device validation still required: None for doctor output.

## 62 — Keep Gradle dependency failures actionable

- Branch: `nightly/android-phone-62-gradle-release-contract`
- Commit: `Clarify phone Gradle dependency failures` (this task's commit)
- Change: Declare namespace, compile SDK, and NDK before Phone dependency
  preflight. Missing 16-KiB or legacy dependencies now produce only their
  intended actionable failure instead of an additional false AGP claim that
  `compileSdk` was absent.
- Tests:
  - `./android/build-phone.sh doctor`: **passed**, all required host tools.
  - Offline Gradle configuration without the 16-KiB sentinel: **expected
    failure**, solely the documented sentinel error; no `compileSdk` error.
  - Offline Gradle configuration with the legacy migration switch but absent
    legacy dependencies: **expected failure**, solely the documented setup
    error; no `compileSdk` error.
  - `android/tests/phone-release-config-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 225/225 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 225/225 host checks.
  - `git diff --check`: **passed**.
- Known risks: Full task-graph configuration remains correctly blocked until
  dedicated dependencies are prepared; no native/package build was attempted.
- Real-device validation still required: None for diagnostic ordering.

## 61 — Prove device lifecycle failures fail closed

- Branch: `nightly/android-phone-61-device-smoke-failures`
- Commit: `Test phone device lifecycle failure paths` (this task's commit)
- Change: Extend the stateful Fake-ADB suite with a PID change during Home and
  a launcher that leaves Phone falsely resumed. The real smoke must reject both
  before recording lifecycle success, complementing its successful-flow test.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including both
    new lifecycle failure fixtures.
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 35
    explicitly device-free suites.
  - `git diff --check`: **passed**.
- Known risks: Mock timing is deliberately instant; vendor scheduling and
  process-management behavior still require real-device coverage.
- Real-device validation still required: Run repeated Home/Back cycles on the
  current APK under normal use and aggressive battery management; any PID
  change or incorrectly resumed activity must fail the smoke.

## 60 — Gate the Android manifest attack surface

- Branch: `nightly/android-phone-60-scope-audit`
- Commit: `Gate phone manifest permissions and exports` (this task's commit)
- Change: Extend the structured data-protection test from backup XML to an
  exact five-permission allowlist, exactly two Activities with only the launcher
  exported, and rejection of aliases, providers, receivers, or services. New
  Android entry points now require an explicit reviewed contract change.
- Tests:
  - `android/tests/phone-data-protection-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 224/224 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 224/224 host checks.
  - Python syntax and `git diff --check`: **passed**.
- Known risks: Gradle dependencies can contribute to the merged manifest; the
  final packaged-manifest review remains necessary in release CI.
- Real-device validation still required: Confirm microphone denial still allows
  world access and microphone grant enables voice; no device test is needed for
  the source XML allowlist itself.

## 59 — Require explicit release version names

- Branch: `nightly/android-phone-59-release-metadata-gate`
- Commit: `Validate phone release version names` (this task's commit)
- Change: Extend the task-graph release gate so APK and AAB outputs require an
  explicit `RELEASE_NUMBER`, bounded to 1–100 portable Android version-name
  characters and beginning alphanumerically. Debug builds retain their local
  default, while release artifacts can no longer silently ship as `0.1.0`.
- Tests:
  - `android/tests/phone-release-config-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 221/221 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 221/221 host checks.
  - `git diff --check`: **passed**.
- Known risks: Play version-code monotonicity still requires external release
  state; this local gate can validate only form and presence.
- Real-device validation still required: None specific to version metadata;
  inspect the signed artifact and Play internal-test listing before promotion.

## 58 — Create the device summary atomically

- Branch: `nightly/android-phone-58-atomic-device-summary`
- Commit: `Create phone device summaries atomically` (this task's commit)
- Change: Close the check/create race at `summary.txt` with shell noclobber, so
  a file or symlink appearing after validation cannot be overwritten or
  followed. The end-to-end Fake-ADB suite now proves a symlink target remains
  unchanged and installation never starts on this failure path.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**, including the
    new protected symlink fixture.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 220/220 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 220/220 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Atomic creation prevents local overwrite races; filesystem-level
  integrity of a caller-owned parent directory remains the caller's concern.
- Real-device validation still required: None specific to atomic file creation;
  the broader current-APK lifecycle smoke remains pending.

## 57 — Mock the complete unattended device smoke

- Branch: `nightly/android-phone-57-device-smoke-mock`
- Commit: `Test unattended phone smoke with mock ADB` (this task's commit)
- Change: Add a stateful fake-ADB regression suite that executes the real device
  smoke without hardware or delays. It covers installation provenance, launch,
  deep link, three Home cycles, Back recovery, private aggregate output, digest
  mismatch rejection, and refusal to overwrite an existing summary.
- Tests:
  - `android/tests/phone-device-smoke-mock-test.sh`: **passed**.
  - `android/tests/phone-static-regression-test.sh`: **passed**, 35 device-free
    suites including the new end-to-end smoke mock.
  - `git diff --check`: **passed**.
- Known risks: The mock proves orchestration and fail-closed contracts, not
  vendor-specific ADB/dumpsys formatting or real Android lifecycle timing.
- Real-device validation still required: Run the same smoke using a current,
  provenance-verified Phone APK and compare its aggregate flags with the mock's
  expected success contract; retain no raw device output.

## 56 — Keep device smoke reports private

- Branch: `nightly/android-phone-56-private-device-reports`
- Commit: `Harden phone device report creation` (this task's commit)
- Change: Require writable/searchable external report directories, refuse an
  existing or symlinked `summary.txt`, and create the aggregate report with
  owner-only permissions. This prevents accidental disclosure or overwrite via
  a caller-selected report directory while preserving all data minimization.
- Tests:
  - `bash -n android/tests/phone-device-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 218/218 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 218/218 host checks.
  - `git diff --check`: **passed**.
- Known risks: Callers that intentionally reused one report directory must now
  select a fresh directory or remove/archive its previous summary first.
- Real-device validation still required: Run against a fresh private report
  directory and confirm mode 0600; then retry with an existing file and a
  summary symlink and confirm both abort before installing the APK.

## 55 — Exercise repeatable device lifecycle stress

- Branch: `nightly/android-phone-55-device-lifecycle-stress`
- Commit: `Extend unattended phone lifecycle smoke` (this task's commit)
- Change: Expand the deterministic device smoke from one Home transition to
  three background/foreground cycles and one unconsumed Back/background/reopen
  cycle. Every phase requires the original native process, and dumpsys state
  must prove that the Phone activity really left and regained the foreground.
- Tests:
  - `bash -n android/tests/phone-device-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 215/215 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 215/215 host checks.
  - `git diff --check`: **passed**.
- Known risks: Vendor launchers and power managers can expose lifecycle timing
  differences; bounded waits deliberately turn those differences into a clear
  device-test failure rather than a silent pass.
- Real-device validation still required: Run this exact smoke against a
  provenance-verified current APK on gesture- and three-button-navigation
  phones; confirm all three Home cycles and Back recovery retain one PID.

## 54 — Verify the package actually installed on the phone

- Branch: `nightly/android-phone-54-device-smoke-integrity`
- Commit: `Verify installed phone APK provenance` (this task's commit)
- Change: After unattended installation, the device smoke resolves exactly one
  private `base.apk`, validates its path, streams it directly into the host
  SHA-256 tool, and requires its digest to equal the requested APK. Reports only
  record the digest and a boolean verification result, never the device path.
- Tests:
  - `bash -n android/tests/phone-device-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 211/211 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 211/211 host checks.
  - `git diff --check`: **passed**.
- Known risks: Some unusually restricted Android builds may deny streaming their
  installed APK even though installation itself succeeds; this intentionally
  fails closed because provenance would otherwise be unverified.
- Real-device validation still required: Run the smoke with an APK built from
  this exact commit and confirm `installed_apk_verified=1`; separately corrupt
  or substitute the input in an isolated test setup and confirm a mismatch is
  rejected without printing the private package path.

## 53 — Gate the final release App Bundle

- Branch: `nightly/android-phone-53-release-bundle-gate`
- Commit: `Gate phone release bundle contents` (this task's commit)
- Change: Normalize AAB `base/manifest`, `base/dex`, `base/assets`, and `base/lib`
  paths into the same strict package contract as APKs. `bundleRelease` now
  requires exactly one task-produced AAB and checks its manifest, dex, ARM64
  runtimes, QML declarations, cache bundles, and synchronized default scripts.
  ZIP alignment remains correctly limited to final APK outputs.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, including a complete
    synthetic AAB and a missing-runtime AAB failure alongside all APK fixtures.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 207/207 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 207/207 host checks.
  - Python syntax and `git diff --check`: **passed**.
- Known risks: A full `bundleRelease` remains blocked by absent dedicated Phone
  dependencies and signing/version inputs; bundletool-generated split APKs need
  their own pipeline install test.
- Real-device validation still required: Generate/install a universal or device
  split APK set from the gated AAB with bundletool, record its digest(s), and run
  the complete unattended smoke on representative API/ABI devices.

## 52 — Make the device smoke test unattended

- Branch: `nightly/android-phone-52-device-permission-automation`
- Commit: `Automate phone smoke test permissions` (this task's commit)
- Change: Install the test artifact with ADB `-r -g`, preventing the main smoke
  path from blocking on Android's microphone dialog, and record the automatic
  runtime-permission grant in the external summary. Permission denial/revocation
  remains an explicit separate lifecycle test rather than hidden human input.
- Tests:
  - `bash -n android/tests/phone-device-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 204/204 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 204/204 host checks.
  - `git diff --check`: **passed**.
- Known risks: The smoke install changes runtime permission state on its test
  package as declared; deny/don't-ask-again/regrant paths require separate runs.
- Real-device validation still required: Run the current APK through this smoke
  from both fresh and previously denied states and confirm it reaches the Qt
  Activity without a dialog or human action; separately automate revoke/deny.

## 51 — Record device-test APK provenance

- Branch: `nightly/android-phone-51-device-apk-provenance`
- Commit: `Record phone device test APK digest` (this task's commit)
- Change: Hash the exact resolved APK before installation, validate a lowercase
  64-digit SHA-256, and write only that digest plus package name to the external
  device-test summary. Future results can be tied to an artifact without
  exposing local paths, device identifiers, or raw logs.
- Tests:
  - `bash -n android/tests/phone-device-test.sh`: **passed**.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 202/202 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 202/202 host checks.
  - `git diff --check`: **passed**.
- Known risks: SHA-256 identifies content but does not establish signer trust;
  release signing/provenance remains an external pipeline responsibility.
- Real-device validation still required: **not executed for this task** because
  no current APK exists. On the next current-build run, confirm the summary
  digest matches the locally gated APK before accepting device results.

## 50 — Synchronize Phone startup scripts and APK gate

- Branch: `nightly/android-phone-50-default-script-sync`
- Commit: `Keep phone startup APK contract synchronized` (this task's commit)
- Change: Parse `PHONE_DEFAULT_SCRIPTS`, add the selector/default require entry,
  compare the exact script set to `REQUIRED_CACHED_ASSETS`, and require every
  corresponding source file. Future startup additions/removals cannot leave the
  APK gate missing a script or carrying a stale mandatory entry.
- Tests:
  - `android/tests/phone-script-payload-test.sh`: **passed**, reporting 13/13
    synchronized startup scripts and all payload exclusions.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 200/200 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 200/200 host checks.
  - Python syntax and `git diff --check`: **passed**.
- Known risks: Parsing deliberately targets the simple literal startup array;
  making it dynamic will fail the test and require an explicit new contract.
- Real-device validation still required: **none specific**; the synchronized
  scripts remain covered by final APK startup and per-app smoke tests.

## 49 — Require the Phone default-script payload

- Branch: `nightly/android-phone-49-apk-default-scripts`
- Commit: `Require phone default scripts in APK` (this task's commit)
- Change: Extend start-critical cached assets to the Phone default-script
  selector and every directly included touch/action-bar/tablet/Emote/Shield/
  People/Avatar/Places/Home runtime, including `androidControls`. APK fixtures
  import this exact checker set so additions cannot silently diverge.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, with every required
    cached script present in valid fixtures and covered by cache/ZIP checks.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 199/199 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 199/199 host checks.
  - Python syntax and `git diff --check`: **passed**.
- Known risks: Transitive `Script.require/include` assets below these roots are
  still protected by the complete cache-manifest presence check, but not each
  named individually as a start-critical top-level entry.
- Real-device validation still required: Covered by the cumulative cold/warm
  start and each-default-app smoke test on the final gated APK.

## 48 — Require extraction of packaged resource bundles

- Branch: `nightly/android-phone-48-apk-cache-contract`
- Commit: `Require phone resource bundle extraction` (this task's commit)
- Change: Require `resources.rcc` and `android_rcc_bundle.rcc` not only to exist
  in the APK but also to appear in `cache_assets.txt`. A package whose bundles
  cannot reach the application cache now fails before install rather than
  passing content checks and failing during native/QML startup.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, with corrected
    complete fixtures and an explicit present-in-APK/but-omitted-from-cache case.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 196/196 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 196/196 host checks.
  - Python syntax and `git diff --check`: **passed**.
- Known risks: Raw QML module files are consumed through the generated RCC and
  therefore intentionally need not all be extracted individually.
- Real-device validation still required: Covered by the cumulative cold-start
  and QML-module smoke test on the final gated APK; no separate hardware-only
  behavior is introduced.

## 47 — Reject ambiguous or multi-ABI Phone APKs

- Branch: `nightly/android-phone-47-apk-archive-uniqueness`
- Commit: `Reject ambiguous phone APK entries` (this task's commit)
- Change: Inspect raw ZIP names before set conversion and fail on duplicates,
  preventing archive/loader ambiguity. Reject every native entry outside
  `lib/arm64-v8a/`, enforcing the Gradle ARM64-only contract against stale or
  injected multi-ABI package output.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, including explicit
    duplicate-entry and unexpected-x86_64 fixtures plus all completeness cases.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 194/194 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 194/194 host checks.
  - Python syntax and `git diff --check`: **passed**.
- Known risks: Non-native archive paths remain allowed unless governed by their
  specific resource/cache contracts; Android signing verification is outside
  this unsigned local package-content gate.
- Real-device validation still required: **none specific**. The cumulative
  gated APK still needs install/start tests on ARM64 phones; archive rejection
  is completely covered by host fixtures.

## 46 — Require core native APK runtimes

- Branch: `nightly/android-phone-46-apk-core-runtimes`
- Commit: `Require core phone APK runtimes` (this task's commit)
- Change: Extend the final APK completeness gate to require `libc++_shared.so`
  and the Qt Core, QML, and Quick ARM64 libraries in addition to the app,
  OpenSSL, PositioningQuick, and every declared plugin. Incremental/stale APKs
  missing a fundamental loader dependency now fail before install.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, with a generated
    omission fixture for every base/declaration runtime including all four new
    entries, plus QML/cache failure fixtures.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 192/192 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 192/192 host checks.
  - Python syntax and `git diff --check`: **passed**.
- Known risks: This is a reviewed start-critical subset, not a general ELF
  `DT_NEEDED` resolver; Android system libraries and preloaded versioned OpenSSL
  SONAMEs make such a resolver a separate task.
- Real-device validation still required: **not executed for this task**. Install
  the gated APK on API 26 and current API devices, cold-start before/after OS
  reboot, and confirm no linker/Qt loader error using PID-filtered aggregates.

## 45 — Validate People success payloads

- Branch: `nightly/android-phone-45-people-payload-validation`
- Commit: `Validate People directory payloads` (this task's commit)
- Change: Treat absent/non-array connection lists as empty, iterate only actual
  arrays, and skip individual records without an object/string username shape.
  Missing location/images objects now produce empty optional fields rather than
  property errors after a formally successful server response.
- Tests:
  - `android/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable successful-response-with-null-data callback and directory/record
    shape contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: This intentionally degrades malformed directory records to absent
  People metadata; server schema monitoring remains an operational concern.
- Real-device validation still required: **not executed for this task**. With a
  controlled test endpoint, return null/missing/mixed-invalid `users`, then a
  valid response; verify People remains open, displays valid rows only, recovers
  on refresh, and emits no private payload detail in logs.

## 44 — Validate People server responses

- Branch: `nightly/android-phone-44-people-response-validation`
- Commit: `Validate People server responses` (this task's commit)
- Change: Centralize success/failure extraction for friend, connection, and
  directory requests so a missing response fails closed without dereferencing
  `status`. Require profile-page content to be a string before regex matching.
  Phone privacy suppression continues to prevent response details in logs.
- Tests:
  - `android/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable missing-response callback and profile-content type contract.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Backend payload schemas after a declared successful response
  remain service contracts; this task covers absent/error response envelopes.
- Real-device validation still required: **not executed for this task**. During
  People refresh and relationship actions, interrupt networking and switch
  metaverse availability; verify no script restart, bounded UI failure behavior,
  retry success, and no response/user details in Phone logs.

## 43 — Own Places portal resources

- Branch: `nightly/android-phone-43-places-portal-ownership`
- Commit: `Own Places portal timers and entities` (this task's commit)
- Change: Enforce the documented 15-portal ceiling with `<` instead of an
  off-by-one `<=`, track every 45-second expiry timer by portal entity, remove
  ownership when it fires, and cancel/delete all remaining timers/entities when
  Places shuts down. No local portal can outlive its owning system script.
- Tests:
  - `android/tests/phone-tablet-places-test.sh`: **passed**, covering exact
    limit, timer registration, expiry ownership, callback cancellation, entity
    deletion, and cleanup invocation contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including portal
    entity lifecycle, all tablet/APK suites, and 188/188 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: The shared Messages channel intentionally supports portals from
  other users; existing distance, schema, duration, and count limits remain.
- Real-device validation still required: **not executed for this task**. Rezz
  16 portals and verify at most 15 exist, wait for expiry and rezz again, then
  stop/restart Places while portals are live and confirm immediate cleanup with
  no delayed callback errors or orphan sound/particle children.

## 42 — Bound Avatar resource URLs

- Branch: `nightly/android-phone-42-avatar-url-contract`
- Commit: `Validate Avatar resource URLs` (this task's commit)
- Change: Apply one non-empty, 4096-character, control-character-free contract
  to custom wearable and external avatar URLs before native resource loaders,
  and mirror the length in both custom URL text fields. Scheme acceptance stays
  with the established resource system so ATP/HTTP/file workflows are preserved.
- Tests:
  - `android/tests/phone-tablet-avatar-test.sh`: **passed**, covering shared URL
    validation, both action boundaries, and QML input lengths.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Reachability and content trust remain native resource-system
  responsibilities; this change bounds transport shape, not remote content.
- Real-device validation still required: **not executed for this task**. Apply
  valid ATP/HTTPS avatar and wearable URLs, blank/overlong/control test inputs,
  Cancel/Back/reopen, and verify errors are bounded with no load or stale IME.

## 41 — Remove the dead Phone Community avatar action

- Branch: `nightly/android-phone-41-avatar-community-boundary`
- Commit: `Hide unavailable Community avatars on phone` (this task's commit)
- Change: Add a QFileSelector presentation contract that prevents construction
  of the `Get More Avatars` Community tile on Phone, where it only opened a
  coming-soon dialog and external marketplace navigation is intentionally
  unavailable. Desktop and Pico retain the tile; Phone favorites/pagination and
  custom avatar/wearable URLs remain available.
- Tests:
  - `android/tests/phone-tablet-avatar-test.sh`: **passed**, covering Phone
    omission, shared construction gate, and Desktop/Pico preservation.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - `git diff --check`: **passed**.
- Known risks: The hidden tile should return only after Phone has an approved,
  native touch marketplace/community surface and a tested external-navigation
  policy.
- Real-device validation still required: **not executed for this task**. Check
  empty, partial, and full favorite pages; verify no Community tile or blank
  phantom cell, pagination remains correct, and Desktop/Pico still show it.

## 40 — Shorten Phone credential lifetime

- Branch: `nightly/android-phone-40-login-credential-lifetime`
- Commit: `Shorten phone login credential lifetime` (this task's commit)
- Change: Clear password text synchronously when Phone login dismisses and clear
  username, password, and local error text again in the destruction fallback.
  Bound each QML credential field to a generous 4096 characters to prevent
  accidental/untrusted unbounded retention without affecting normal accounts.
- Tests:
  - `android/tests/phone-dialog-routing-test.sh`: **passed**, including bounded
    fields, synchronous password clearing, and destruction-fallback clearing.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including the C++
    async login contract, all tablet/lifecycle/APK suites, and 188/188 host checks.
  - `git diff --check`: **passed**.
- Known risks: The account managers necessarily retain their own request copy
  while authentication is in flight; this task only minimizes QML field lifetime.
- Real-device validation still required: **not executed for this task**. Submit
  valid/invalid credentials, retry after failure, Cancel while pending, Back,
  background/foreground, and reopen; verify retry usability, empty fields after
  every dismissal, no stale errors, and no credential text in screenshots/logs.

## 39 — Validate Phone address input

- Branch: `nightly/android-phone-39-address-input-contract`
- Commit: `Validate phone address input` (this task's commit)
- Change: Bound the screen-space address field to 4096 characters, trim only
  surrounding whitespace, and reject blank/control-character input before the
  QML/C++ lookup boundary. Invalid input keeps the dialog and keyboard focus
  with a bounded local error; valid place names containing spaces remain valid.
- Tests:
  - `android/tests/phone-dialog-routing-test.sh`: **passed**, including maximum
    length, normalization, control-character, local-error, and validated-value
    delegation contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - `git diff --check`: **passed**.
- Known risks: QML source contracts cannot reproduce every Android IME action;
  final lookup semantics remain owned by AddressManager.
- Real-device validation still required: **not executed for this task**. Test
  placenames with spaces, hifi/overte URLs, paths and network addresses; verify
  blank/overlong/control input stays open with an error, Return and Go navigate
  once, and Back/Cancel/external teardown always hides the IME.

## 38 — Validate Avatar scale/settings state

- Branch: `nightly/android-phone-38-avatar-scale-contract`
- Commit: `Validate Avatar scale and settings state` (this task's commit)
- Change: Require an initialized current-avatar model plus a finite positive
  numeric scale before preview/revert/save mutations, and require a settings
  object before dereferencing it. Rejected actions return bounded QML errors
  instead of throwing or passing NaN/Infinity into native avatar state.
- Tests:
  - `android/tests/phone-tablet-avatar-test.sh`: **passed**, including scale
    type/finiteness/range, initialized-model, settings-object, and error contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Native avatar-scale clamping remains authoritative for the upper
  product range; this boundary rejects only values that are intrinsically unsafe.
- Real-device validation still required: **not executed for this task**. Open
  Avatar Settings before/after bookmark loads, drag scale, Cancel/revert, Save,
  and rapidly close/reopen; confirm finite scale persistence, no stale preview,
  and a responsive UI after malformed test-bridge messages.

## 37 — Validate People account actions

- Branch: `nightly/android-phone-37-people-request-validation`
- Commit: `Validate People account action inputs` (this task's commit)
- Change: Require non-empty, bounded, control-character-free string account
  names before add/remove-friend or remove-connection requests. Encode names
  inserted into REST paths as one URI segment so reserved characters cannot
  alter the endpoint; valid request bodies and response handling are unchanged.
- Tests:
  - `android/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable mock proving invalid names issue no request and `user/name`
    reaches the connection endpoint as `user%2Fname`.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Backend username semantics may be narrower than the transport
  safety contract; the server remains authoritative for valid names.
- Real-device validation still required: **not executed for this task**. With
  disposable test accounts, add/remove friends and remove a connection whose
  valid name contains every backend-supported punctuation character; verify one
  request/action, correct UI update, and no private values in Phone logs.

## 36 — Own deferred Phone menu actions

- Branch: `nightly/android-phone-36-menu-deferred-action`
- Commit: `Harden deferred phone menu actions` (this task's commit)
- Change: Give the zero-delay menu action timer explicit cancel/replace
  semantics, clear it whenever the menu stack is replaced, detach its item
  reference before execution, and revalidate the Phone allow/deny policy at
  callback time. A stale touch can no longer trigger an action after Home/menu
  replacement or after the action becomes unsupported.
- Tests:
  - `android/tests/phone-tablet-people-menu-test.sh`: **passed**, including timer
    ownership, replacement cancellation, reference detachment, and execution-
    time Phone-policy contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - `git diff --check`: **passed**.
- Known risks: QML Timer scheduling is source-contract tested; actual event-loop
  ordering during rapid multi-touch remains device-specific.
- Real-device validation still required: **not executed for this task**. Tap
  allowed and unavailable menu rows while immediately pressing Home/Back or
  reopening Menu; confirm allowed actions fire once only while still current,
  unavailable/stale actions never fire, and the menu remains responsive.

## 35 — Invalidate the Phone asset cache by content

- Branch: `nightly/android-phone-35-content-cache-stamp`
- Commit: `Use content digest for phone asset cache` (this task's commit)
- Change: Replace Phone's maximum-mtime extraction marker with a deterministic
  SHA-256 over sorted asset paths and bytes, and reject duplicate paths while
  generating the manifest. The shared Android extractor accepts this 64-digit
  lowercase hex marker plus the legacy 1–19 digit timestamp, preserving Pico
  compatibility while ensuring changed Phone assets are never skipped merely
  because another file has a newer mtime.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, covering legacy and
    content-digest markers plus short, non-hex, oversized, non-ASCII, duplicate,
    traversal, missing-asset, native-runtime, and QML-asset failures.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 188/188 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/APK suites and 188/188 host checks.
  - `git diff --check`: **passed**.
- Known risks: Full Gradle asset merging is blocked by absent Phone dependencies;
  hashing adds one sequential read of the packaged cache assets during build.
  The common extractor's legacy numeric branch is intentionally retained.
- Real-device validation still required: Build two APKs whose changed asset is
  older than an unchanged asset, install both with `-r`, and verify the second
  start extracts and uses the changed script/QML. Confirm upgrade from a legacy
  timestamp-marker APK also re-extracts once and starts normally.

## 34 — Escape generated Phone QML resource XML

- Branch: `nightly/android-phone-34-qml-qrc-escaping`
- Commit: `Escape generated phone QML resource paths` (this task's commit)
- Change: XML-escape both QRC aliases and absolute source paths when Gradle
  generates the Phone QML resource manifest. Worktrees or dependency paths
  containing XML metacharacters can no longer corrupt `phone-qml.qrc` before
  `rcc` runs; packaged modules and runtime paths are unchanged.
- Tests:
  - `android/tests/phone-host-regression-test.sh`: **passed**, including escape
    helper, metacharacter, and absolute-path-use contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle suites and 185/185 host checks.
  - `git diff --check`: **passed**.
- Known risks: A full Gradle merge-assets run is blocked by the absent Phone
  dependency graph. Groovy interpolation and standard XML entities are covered
  statically rather than by invoking `rcc` in this worktree.
- Real-device validation still required: **none specific**. The resulting APK
  still requires the cumulative install/start/Qt-QML-module smoke tests; this
  build-path fix itself is host-verifiable.

## 33 — Defer deep links received in the background

- Branch: `nightly/android-phone-33-background-deep-link`
- Commit: `Defer phone deep links until resume` (this task's commit)
- Change: Do not hand a new singleTask deep link to native navigation while the
  Phone Activity is paused. Retain only the latest normalized destination and
  drain it from `onResume`; Activity destruction also clears retry callbacks
  explicitly before parent teardown.
- Tests:
  - `android/tests/phone-app-lifecycle-test.sh`: **passed**, including ordered
    background-retention and destroy-cleanup contracts.
  - `android/tests/phone-deep-link-test.sh`: **passed**, 20 JVM assertions.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle suites and 182/182 host checks.
  - `git diff --check`: **passed**.
- Known risks: Android framework scheduling is represented by ordered source
  contracts; native delivery still intentionally retains only the latest link.
- Real-device validation still required: **not executed for this task**. Put
  Overte in background, deliver two neutral test links, verify no world changes
  while backgrounded and only the latest applies once after foreground; repeat
  across Activity recreation and process restart.

## 32 — Own the complete Android Back gesture

- Branch: `nightly/android-phone-32-back-repeat-lifecycle`
- Commit: `Keep consumed Back repeats out of Qt` (this task's commit)
- Change: When native/QML navigation consumes the initial Android Back Down,
  consume every long-press repeat until the matching Up. A single physical
  gesture can no longer leak repeat events into Qt and close additional layers
  or background the task. Unconsumed Back gestures retain legacy handling.
- Tests:
  - `android/tests/phone-app-lifecycle-test.sh`: **passed**, including an
    ordered source contract for initial Down, native decision, repeat ownership,
    matching Up, and pause-state reset.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: Host tests cannot synthesize Android framework KeyEvent dispatch;
  the change follows the Activity's existing per-gesture boolean state.
- Real-device validation still required: **not executed for this task**. Use
  short and long Back presses in Address, Login, Settings subpages, tablet Home,
  and world view; verify each gesture closes at most one layer and an unhandled
  gesture backgrounds rather than terminates the native process.

## 31 — Bound the Quick Goto Home contract

- Branch: `nightly/android-phone-31-quick-goto-contract`
- Commit: `Bound phone Quick Goto destinations` (this task's commit)
- Change: Limit the persisted Home destination to 4096 characters before it
  crosses into address lookup. Missing, non-string, blank, control-character,
  and overlong values all fail closed to packaged tutorial content; valid Home
  navigation and the direct Tutorial action are unchanged.
- Tests:
  - `android/tests/phone-tablet-quick-goto-test.sh`: **passed**, including an
    executable mock for button registration, valid Home lookup, packaged
    Tutorial, malformed/overlong fallback, and tablet close on every action.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle suites and 181/181 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Address scheme/domain policy remains owned by the established
  AddressManager lookup path rather than duplicated in this small launcher.
- Real-device validation still required: **not executed for this task**. Test
  valid and unset Home bookmarks plus Tutorial, confirm each closes the tablet,
  navigates once, and repeated taps do not leave an unresponsive surface.

## 30 — Scope the Shield menu preference away from Phone

- Branch: `nightly/android-phone-30-shield-menu-scope`
- Commit: `Remove desktop Shield preference from phone` (this task's commit)
- Change: Do not register, connect, disconnect, or remove the desktop `HUD
  Shield Button` Settings preference on Android Phone. Phone retains its direct
  SHIELD tablet action and world feedback; Desktop and Pico retain the HUD
  preference and its established lifecycle.
- Tests:
  - `node --check scripts/system/bubble.js`: **passed**.
  - `android/tests/phone-tablet-shield-test.sh`: **passed**, including guarded
    setup/teardown and Desktop/Pico preservation contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, portal lifecycle suite, and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: Phone has one intentional Shield entry point instead of the
  desktop HUD visibility preference; Shield enabled state remains owned by the
  existing Users interface.
- Real-device validation still required: **not executed for this task**. Confirm
  Settings contains no HUD Shield preference, SHIELD toggles the privacy radius
  in both directions, closes the tablet, renders feedback, and survives rapid
  taps plus app background/foreground.

## 29 — Own the Places portal entity lifecycle

- Branch: `nightly/android-phone-29-portal-entity-lifecycle`
- Commit: `Harden Places portal entity lifecycle` (this task's commit)
- Change: Make the packaged portal entity script reject invalid JSON, missing or
  bounded-invalid text, and non-finite dimensions before creating child
  entities. Entering an invalid portal is inert; repeated enter events own one
  teleport timer; entity unload cancels it and prevents delayed navigation.
- Tests:
  - `android/tests/phone-tablet-portal-lifecycle-test.sh`: **passed**, including
    JavaScript syntax and an executable invalid/valid preload, repeated-entry,
    unload-cancellation, completed-navigation, and deletion mock.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including the new
    portal suite, all tablet suites, and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: The mock does not render particles/text or play real Android
  audio. Portal URLs use the same bounded address contract as their creator,
  while final scheme handling remains the established `Window.location` path.
- Real-device validation still required: **not executed for this task**. Create
  a portal, enter once and confirm sound plus delayed navigation; rapidly cross
  its boundary repeatedly and confirm one transition; delete/unload it during
  the delay and confirm no later navigation or orphan child/audio entities.

## 28 — Validate Places portal contracts

- Branch: `nightly/android-phone-28-places-portal-validation`
- Commit: `Validate Places portal messages` (this task's commit)
- Change: Reuse the bounded, control-character-free destination contract before
  broadcasting a QML portal request and before creating a received portal.
  Received portal positions must also be objects with finite numeric x/y/z
  coordinates before any Vec3 operation or local entity creation.
- Tests:
  - `node --check scripts/system/places/places.js`: **passed**.
  - `android/tests/phone-tablet-places-test.sh`: **passed**, including outgoing
    destination and incoming address/finite-position contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: Portal display names and place identifiers are serialized as
  inert user data; their semantic trust remains a domain/application concern.
- Real-device validation still required: **not executed for this task**. From
  Phone Places request a valid portal, verify its local placement and expiry,
  then use a test script to send missing, non-finite, and overlong portal data
  and confirm no entity appears and the client remains responsive.

## 27 — Validate Avatar message boundaries

- Branch: `nightly/android-phone-27-avatar-message-validation`
- Commit: `Validate Avatar app message boundaries` (this task's commit)
- Change: Ignore null, scalar, method-less, and non-string-method QML messages;
  reject navigation without a string URL with a bounded UI error; and ignore
  valid JSON scalars/null at the object-manipulation channel before accessing
  their fields. Valid local avatar, bookmark, wearable, and web behavior is
  unchanged.
- Tests:
  - `node --check scripts/system/avatarapp.js`: **passed**.
  - `android/tests/phone-tablet-avatar-test.sh`: **passed**, including explicit
    QML, navigation, and manipulation-message boundary contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: Source-contract tests do not instantiate the large shared Avatar
  dependency graph. Individual operation schemas remain validated by their
  existing action-specific checks.
- Real-device validation still required: **not executed for this task**. Open
  Avatar repeatedly, exercise packaged bookmarks and wearable adjustment, and
  confirm malformed bridge probes neither navigate nor close/restart the app.

## 26 — Validate People message boundaries

- Branch: `nightly/android-phone-26-people-message-validation`
- Commit: `Validate People messages and deferred delivery` (this task's commit)
- Change: Ignore null, method-less, malformed-JSON, and incomplete refresh
  messages at both QML and same-avatar local-message boundaries. People now owns
  the deferred delivery used when a selection opens the app, cancels it on
  close/shutdown, and verifies the surface is still open before delivery.
- Tests:
  - JavaScript syntax checks for PAL and its mock: **passed**.
  - `android/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable mock for malformed messages, valid open, timer ownership,
    cancellation, repeated lifecycle transitions, and shutdown.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: Server response schemas and valid user-operation parameters are
  outside this local-message boundary and still depend on backend contracts.
- Real-device validation still required: **not executed for this task**. Send a
  valid entity selection into a closed People app, immediately Back/Home it,
  and confirm no delayed selection arrives; repeat with rapid reopen and domain
  transitions. Do not use production account data for malformed-input probes.

## 25 — Fail closed for desktop-only Settings menu actions

- Branch: `nightly/android-phone-25-menu-settings-policy`
- Commit: `Block desktop-only Settings actions on phone` (this task's commit)
- Change: Mark `Developer Menu` and `Ask To Reset Settings on Start` unavailable
  in the screen-space Phone tablet. This prevents a touch from exposing a large
  unreviewed desktop developer tree or silently changing the next-start crash
  recovery policy without a Phone-native confirmation flow. Desktop and Pico
  menu behavior is unchanged.
- Tests:
  - `android/tests/phone-tablet-people-menu-test.sh`: **passed**, including
    explicit contracts for both blocked Settings actions.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: The Settings subtree still uses a reviewed denylist after its
  allowlisted root. Newly added desktop actions therefore require continuing
  review; root-level menu additions remain fail-closed automatically.
- Real-device validation still required: **not executed for this task**. Open
  Menu > Settings and confirm both rows are visibly unavailable, cannot toggle,
  and remain inert under rapid taps while General/Audio/Security routes work.

## 24 — Keep People diagnostics private on Phone

- Branch: `nightly/android-phone-24-people-log-privacy`
- Commit: `Suppress private People diagnostics on phone` (this task's commit)
- Change: Route PAL diagnostics that may contain usernames, display names,
  session UUIDs, profile URLs, relationship state, response text, or complete
  nearby-person records through a Phone-aware privacy boundary. Desktop keeps
  its established debug detail; Android Phone emits none of these values into
  logs collected by automated tests or support tooling.
- Tests:
  - `node --check scripts/system/pal.js`: **passed**.
  - `android/tests/phone-tablet-people-menu-test.sh`: **passed**, including
    privacy-boundary and no-direct-personal-log contracts plus the executable
    People lifecycle mock.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: This suppresses potentially private PAL diagnostics rather than
  redesigning the shared logging API. Operational debugging on Phone must rely
  on aggregate/state-only messages.
- Real-device validation still required: **not executed for this task**. In a
  test account and populated domain, exercise People refresh, friendship and
  connection actions, profile pictures, and missing identities; verify only
  aggregate diagnostics and no user/session/profile values reach captured logs.

## 23 — Preserve the bounded Phone graphics profile

- Branch: `nightly/android-phone-23-graphics-settings`
- Commit: `Hide unbounded Graphics Settings on phone` (this task's commit)
- Change: Selector-gate the desktop Graphics page out of Phone Settings and
  put its component behind an inactive Loader, preventing both navigation and
  hidden construction writes. This preserves Phone's bounded native render
  scale, 30-FPS target, forward path, and disabled expensive effects. Desktop
  and Pico retain the complete page and existing layout.
- Tests:
  - `android/tests/phone-tablet-settings-scale-test.sh`: **passed**, 17
    selector, layout, non-construction, and desktop/Pico preservation checks.
  - `android/tests/phone-tablet-app-router-test.sh`: **passed**.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: Runtime graphics experimentation remains available through the
  bounded Android debug properties and benchmark harness, not end-user UI. A
  future Phone graphics page needs device-derived bounds and transactional
  reset behavior before this gate should be reopened.
- Real-device validation still required: **not executed**. Confirm Settings has
  no Graphics row, startup diagnostics retain scale/FPS/effect bounds across
  Settings visits and restarts, and Desktop/Pico builds still show Graphics.

## 22 — Complete Phone Audio controls

- Branch: `nightly/android-phone-22-audio-controls`
- Commit: `Remove inactive phone Audio controls` (this task's commit)
- Change: Remove the redundant single Desktop tab, keyboard-`T` push-to-talk,
  and desktop avatar-audio-tools overlay from the Phone Audio selector while
  retaining mute, stereo, devices, gains, processing, meters, and scrolling.
  Hidden PTT/audio-tools bindings are write-guarded so construction cannot
  mutate their settings. Desktop and VR presentations remain unchanged.
- Tests:
  - `android/tests/phone-tablet-audio-test.sh`: **passed**, 16 Phone/Desktop/VR
    presentation and lifecycle contracts.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - `git diff --check`: **passed**.
- Known risks: Phone currently has no dedicated press-and-hold PTT input. It can
  be reintroduced only with a native touch action and explicit capture/release
  lifecycle, rather than exposing an unusable desktop setting.
- Real-device validation still required: **not executed**. Confirm the Audio
  view starts at its form without a mode strip, contains no PTT/audio-tools/HMD
  controls, and exercises mute, stereo, processing, sliders, input/output device
  selection, peak meters, scrolling, Back, and repeated reopen.

## 21 — Emote close cleanup

- Branch: `nightly/android-phone-21-emote-close-cleanup`
- Commit: `Stop phone Emote animation on close` (this task's commit)
- Change: Treat the transition away from the exact Emote QML surface as an
  ownership boundary. Back, Home, or an app switch now cancels the completion
  timer and restores the avatar animation immediately instead of leaving an
  invisible override running until its nominal frame duration expires.
- Tests:
  - `android/tests/phone-tablet-emote-test.sh`: **passed**, 15 source contracts
    plus the executable lifecycle mock.
  - Lifecycle mock: **passed** for play, same-action stop, surface close,
    timer cancellation, restoration, reopen/play, and script shutdown.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Animation restoration on actual movement still belongs to the
  avatar locomotion system; Phone deliberately does not recreate the legacy
  controller mapping merely to observe movement.
- Real-device validation still required: **not executed**. Start every Emote
  and leave through Back, Home, tablet close, app switch, and backgrounding;
  verify locomotion returns immediately and reopen shows no stale highlight.

## 20 — Settings message source scope

- Branch: `nightly/android-phone-20-settings-message-scope`
- Commit: `Scope phone Settings navigation messages` (this task's commit)
- Change: Require the selector-resolved Settings surface to be the active
  tablet source before accepting even an allowlisted `switchApp` message. Home,
  unrelated QML apps, and a Settings page that has already navigated away can
  no longer reuse the Settings router.
- Tests:
  - `android/tests/phone-tablet-app-router-test.sh`: **passed**, including
    executable Home, unrelated-app, active-Settings, post-navigation, malformed,
    inherited-property, local-file, and remote-URL cases.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Source equality depends on the established Tablet `screenChanged`
  contract, which is already used for button and app lifecycle state throughout
  the client. The route fails closed if that contract changes.
- Real-device validation still required: **not executed**. Navigate rapidly
  among Settings, General, Audio, Security, Home, and Emote; verify Settings
  rows work only while Settings is visible and delayed/crafted messages from a
  previous surface cannot change the current app.

## 19 — Action-bar teardown race

- Branch: `nightly/android-phone-19-actionbar-lifecycle`
- Commit: `Harden phone action bar teardown` (this task's commit)
- Change: Own and cancel the deferred initial-layout timer, reject layout work
  once shutdown starts, tolerate a QML fragment disappearing between a geometry
  signal and teardown, and clear all fragment/button references after closing.
  Existing signal, virtual-pad, and touch-capture cleanup remains deterministic.
- Tests:
  - `android/tests/phone-actionbar-qml-lifetime-test.sh`: **passed**, including
    a new executable mock for deferred-timer cancellation, destroyed-fragment
    geometry, signal teardown, fragment close, and world-control restoration.
  - `android/tests/phone-tablet-routing-test.sh`: **passed**.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: QML fragment destruction timing is mocked; the defensive catch
  intentionally treats a vanished action bar as terminal until script restart.
- Real-device validation still required: **not executed**. Rapidly launch,
  background, foreground, rotate within supported landscape orientations, open
  the tablet, and terminate/restart while layout is pending; confirm no stale
  controls, touch capture, script exception, or post-teardown geometry update.

## 18 — Touch-safe Phone Security Settings

- Branch: `nightly/android-phone-18-security-settings`
- Commit: `Harden phone Security Settings` (this task's commit)
- Change: Add selector-backed compact Security metrics, omit and write-guard
  the incomplete user-managed scripting-plugin control on Phone, and make both
  allowlist editors null-safe, deterministically normalized, duplicate-free,
  responsive above their Save controls, and explicit about IME focus teardown.
  Desktop retains its existing plugin control and dimensions.
- Tests:
  - `android/tests/phone-tablet-security-test.sh`: **passed**, ten source
    contracts plus an executable Node normalization suite covering empty,
    malformed, mixed-separator, duplicate, and prototype-named entries.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites and 181/181 host checks.
  - JavaScript syntax and `git diff --check`: **passed**.
- Known risks: Static layout checks cannot prove keyboard resize or font metrics
  on OEM Qt surfaces. Normalization deliberately treats commas and all
  whitespace as entry separators, matching the C++ allowlist consumers.
- Real-device validation still required: **not executed**. With an entirely
  synthetic allowlist, exercise empty/cancel/edit/save/reopen, multiline input,
  IME show/hide, Back, background/foreground, and both protection switches;
  confirm the scripting-plugin control is absent and no text is clipped.

## 17 — Safe cached-asset extraction

- Branch: `nightly/android-phone-17-cache-manifest-gate`
- Commit: `Harden phone cached asset extraction` (this task's commit)
- Change: Validate the generated `cache_assets.txt` as a fail-closed archive
  manifest and harden the shared Android extractor used by Phone. Cache stamps
  must be bounded ASCII integers; asset entries must be unique safe relative
  paths. Java resolves the cache root and every target canonically and refuses
  any destination outside the app-private cache before creating or replacing a
  file.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, including traversal,
    absolute-path, duplicate-entry, Unicode-digit, and oversized-stamp fixtures.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 181/181 checks,
    including canonical-root and containment contracts for `HifiUtils`.
  - `git diff --check`: **passed**.
- Known risks: The runtime extractor is shared Android code because Phone calls
  it directly; other Android clients receive the same path validation without
  changes to their branches or product-specific files. Archive verification
  remains the first line of defense for Phone builds.
- Real-device validation still required: **not executed**. Install twice from
  clean and warm app cache, confirm assets extract once and are reused, then
  install a newer APK and confirm its new timestamp refreshes assets without a
  startup exception.

## 16 — Declared QML metadata APK gate

- Branch: `nightly/android-phone-16-qml-asset-gate`
- Commit: `Require declared phone QML assets in APK gate` (this task's commit)
- Change: Extend the final APK checker from native QML plugins to the
  `bundled_in_assets` loader contract. Each declared module must contain its
  packaged `qmldir` marker. Absolute/traversing paths, empty declarations, and
  duplicate markers fail closed.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, including twelve
    independently omitted QML-module metadata fixtures in addition to all 25
    native-runtime omissions, the general cached-asset fixture, and three
    malformed/traversing/duplicate declaration fixtures.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 179/179 checks.
  - `git diff --check`: **passed**.
- Known risks: A `qmldir` marker proves module metadata presence, not that every
  optional QML component is packaged. Native plugin presence, cached app assets,
  ELF alignment, and real surface loading remain separate gates.
- Real-device validation still required: **not executed**. Open all Settings,
  dialog, graphical-effect, and native Phone QML surfaces from a clean install;
  confirm no `module ... is not installed` or plugin-loader failure occurs.

## 15 — Declared QML runtime APK gate

- Branch: `nightly/android-phone-15-qml-runtime-gate`
- Commit: `Require declared phone QML runtimes in APK gate` (this task's commit)
- Change: Make the final APK completeness checker consume the Phone
  `qt_dependencies.xml` `bundled_in_lib` array and require every declared
  native Qt/QML plugin. Declarations are validated as ARM64 library basenames;
  malformed, empty, or duplicate entries fail closed. This expands omission
  coverage from nine native runtimes to all 25 current required libraries.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, including a fixture
    omitting each of the 25 native entries independently.
  - `android/tests/phone-host-regression-test.sh`: **passed**, 177/177 checks.
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 34
    explicitly device-free suites.
  - Python source execution through the fixture test: **passed**.
  - `git diff --check`: **passed**.
- Known risks: Archive presence does not prove ABI compatibility or loadability;
  the existing ELF alignment, dependency sentinel, and real launch gates remain
  independently required.
- Real-device validation still required: **not executed**. Build and install a
  clean 16-KiB APK, open every QML-backed Phone surface, and verify that no Qt
  module/plugin loader error appears in PID-filtered diagnostics.

## 14 — Avatar bookmark log privacy

- Branch: `nightly/android-phone-14-bookmark-log-privacy`
- Commit: `Redact phone bookmark parse diagnostics` (this task's commit)
- Change: Stop writing the raw `AvatarBookmarks` parser error to Android logs.
  Phone now emits one fixed aggregate warning; the desktop recovery dialog
  retains its detailed local error because this change is Phone-scoped.
- Tests:
  - `android/tests/phone-host-regression-test.sh`: **passed**, 175/175 checks,
    including a regression rejection for raw parser details in `qWarning`.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet contracts and 175/175 host checks.
  - `git diff --check`: **passed**.
- Known risks: The aggregate warning intentionally sacrifices parser detail in
  persistent Android logs. Debugging malformed bookmark JSON requires a private
  reproduction or an explicitly consented transient diagnostic channel.
- Real-device validation still required: **not required for correctness; not
  executed**. An automated device fixture may corrupt only synthetic bookmark
  data and confirm that logcat contains the fixed warning but not fixture text.

## 13 — Fail-closed Phone Settings routes

- Branch: `nightly/android-phone-13-tablet-route-allowlist`
- Commit: `Restrict phone tablet app navigation` (this task's commit)
- Change: Replace the generic `switchApp.appUrl` loader in the Phone tablet
  registrar with an exact allowlist for the packaged General, Audio, and three
  Security settings surfaces. Both legacy and current General Settings requests
  resolve to the selector-aware tablet page. Unknown local paths, remote URLs,
  inherited object properties, and non-string payloads are ignored.
- Tests:
  - `android/tests/phone-tablet-app-router-test.sh`: **passed**, including the
    executable Node lifecycle mock and ten rejected payload classes.
  - `android/tests/phone-tablet-routing-test.sh`: **passed**.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet contracts and 174/174 host checks.
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 34
    explicitly device-free suites.
  - `git diff --check`: **passed**.
- Known risks: The allowlist intentionally mirrors the Settings QML page list;
  a future first-party page must update both contracts or it will fail closed.
- Real-device validation still required: **not executed**. Open General, Audio,
  Security, QML Allowlist, and Script Security from Settings; verify each opens
  inside the tablet and Back returns safely. Confirm no external URI or desktop
  window can be opened through a crafted `switchApp` message.

## 01 — Host regression from any working directory

- Branch: `nightly/android-phone-01-host-test-cwd`
- Commit: `96af2c70b4` — `Fix phone host regression working directory`
- Change: Resolve the Gradle input of the inline `awk` contract check from the
  script's already-normalized Android root. The advertised root-level command
  now exercises all checks instead of producing a false failure.
- Tests:
  - Before the fix, `./android/tests/phone-host-regression-test.sh`: **failed**,
    173 of 174 checks passed; `awk` could not open
    `apps/phoneInterface/build.gradle` from the repository root.
  - Before the fix, `(cd android && ./tests/phone-host-regression-test.sh)`:
    **passed**, 174 of 174 checks.
  - After the fix, `./android/tests/phone-host-regression-test.sh` from the
    repository root: **passed**, 174 of 174 checks.
  - After the fix, the same absolute script command from `/tmp`: **passed**,
    174 of 174 checks.
  - `git diff --check`: **passed**.
- Known risks: None in runtime code; this changes only a source-based host test.
- Real-device validation still required: **not required for this test-only
  change; not executed**.

## 09 — Phone-specific doctor hand-off

- Branch: `nightly/android-phone-09-doctor-output`
- Commit: `86f4ad08cb` — `Fix Android phone doctor guidance`
- Change: Keep reusing the shared Pico/Phone toolchain checker, but translate
  its heading and successful next step at the Phone wrapper boundary. Preserve
  the original checker exit status through the output filter.
- Tests:
  - `android/tests/phone-doctor-output-test.sh`: **passed**, including shared
    checker status propagation.
  - `bash -n android/build-phone.sh android/tests/phone-doctor-output-test.sh`:
    **passed**.
  - `./android/build-phone.sh doctor`: **passed**, Phone heading and next step,
    all tools found with no warnings.
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 34 suites;
    nested host regression passed 174/174 checks.
  - `git diff --check`: **passed**.
- Known risks: Diagnostic detail still comes from the shared checker by design;
  only the product heading and successful hand-off are Phone-specific.
- Real-device validation still required: **not required for this wrapper-only
  change; not executed**.

## 11 — Remove inactive Phone Privacy controls

- Branch: `nightly/android-phone-11-settings-privacy`
- Commit: `af9e84f984` — `Remove inactive phone privacy settings`
- Change: Remove the shared Privacy category from Phone General Settings. Its
  crash toggle cannot work with the Phone target's `USE_BREAKPAD=OFF`, and its
  Discord toggle resolves to the Android no-op stub. Phone now exposes only
  complete Navigation and touch-look sensitivity categories; other clients are
  unchanged.
- Tests:
  - `android/tests/phone-tablet-general-preferences-test.sh`: passed (10
    contract checks).
  - `android/tests/phone-tablet-static-test.sh`: passed (174 checks plus
    focused tablet suites).
  - `android/tests/phone-static-regression-test.sh`: passed (34 explicitly
    device-free suites).
  - `git diff --check`: passed.
- Known risks: The generic activity-data preference is hidden together with
  its two inactive category siblings because individual hidden controls are
  still loaded/saved by the shared dialog. Reintroducing it safely requires a
  Phone-specific complete category or per-preference construction filter.
- Real-device validation still required: **not executed**. Confirm General
  Settings shows exactly Navigation and Mouse Sensitivity, saves/cancels both,
  scrolls correctly, and exposes no crash or Discord controls.

## 10 — Places navigation input and log privacy

- Branch: `nightly/android-phone-10-deep-link-audit`
- Commit: `c513546a1e` — `Harden phone Places navigation messages`
- Change: Validate Phone Places QML teleport destinations before any property
  use or navigation: require a non-empty string, cap it at 4096 UTF-16 units,
  and reject raw control characters. Remove the diagnostic that logged the
  destination and user-visible place name. The exported Android deep-link
  normalizer was audited and already has equivalent scheme/size/raw-character
  boundaries, so it was not changed.
- Tests:
  - `android/tests/phone-tablet-places-test.sh`: **passed**, 24 checks.
  - `node --check scripts/system/places/places.js`: **passed**.
  - `android/tests/phone-deep-link-test.sh`: **passed**, 20 Java assertions.
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 34 suites;
    nested host regression passed 174/174 checks.
  - `git diff --check`: **passed**.
- Known risks: Static contracts cannot execute a real destination transition;
  the QML surface only emits entries obtained from the guarded directory path.
- Real-device validation still required: **not executed**. Open Places with
  normal, maximum-length, Unicode, offline, and malformed federation results;
  tap destinations repeatedly and confirm valid navigation, invalid-message
  no-op behavior, and absence of destination/name text in app diagnostics.

## 08 — Complete required-runtime APK gate

- Branch: `nightly/android-phone-08-error-path-audit`
- Commit: `5d62ce29de` — `Require phone runtime libraries in APK gate`
- Change: Require all explicitly staged Phone runtime libraries in the final
  APK content checker: client, PositioningQuick, OpenSSL crypto/TLS, platform,
  bearer, JPEG/SVG image, and OpenSL ES audio. Generate and reject a fixture
  omitting each required native entry independently.
- Tests:
  - `android/tests/phone-apk-contents-test.sh`: **passed**, including 9
    independently omitted native-runtime fixtures plus the asset fixture.
  - `python3 -m py_compile android/tests/check-phone-apk-contents.py`:
    **passed**; generated bytecode was removed afterward.
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 33 suites;
    nested host regression passed 174/174 checks.
  - `./android/build-phone.sh doctor`: **passed**, all tools found with no
    warnings. A full APK build was **not run** because the dedicated Phone Qt
    and non-Qt 16-KiB outputs and readiness sentinel are absent; the build is
    designed to stop before compiling in that state.
  - `git diff --check`: **passed**.
- Known risks: The fixture proves archive completeness, not loader/ABI
  compatibility; ELF alignment and dependency-sentinel gates remain separate.
- Real-device validation still required: **not executed**. Install a clean APK,
  verify cold launch, TLS login/deep link, Places networking, SVG/JPEG tablet
  assets, audio output/input, and confirm no native-loader errors in the
  PID-filtered app diagnostics.

## 07 — Fail-closed backup and device transfer

- Branch: `nightly/android-phone-07-packaging-audit`
- Commit: `890816d373` — `Exclude all phone backup data domains`
- Change: Preserve `allowBackup=false` and explicitly exclude every supported
  credential- and device-protected domain from both the legacy full-backup
  format and Android 12+ cloud/device-transfer rules. Add an XML parser test
  that rejects missing, duplicate, included, or custom-agent escape paths.
- Tests:
  - `android/tests/phone-data-protection-test.sh`: **passed**, all 9 domains in
    all three rule sections.
  - `android/tests/phone-release-config-test.sh`: **passed**.
  - Python bytecode compilation and `xmllint --noout` for both rule files and
    the manifest: **passed**; generated bytecode was removed afterward.
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 33 suites;
    nested host regression passed 174/174 checks.
  - `git diff --check`: **passed**.
- Known risks: OEM backup behavior can deviate from AOSP; redundant manifest
  and per-domain rules intentionally express the same deny policy.
- Real-device validation still required: **not executed**. On API 26–30 and
  API 31+ test `bmgr`/OEM cloud backup and cable/device-to-device migration,
  then confirm no account token, settings, database, cached asset, or external
  app file appears on the destination device.

## 06 — Complete device-free regression gate

- Branch: `nightly/android-phone-06-complete-static-gate`
- Commit: `ff856ab078` — `Add complete phone static regression gate`
- Change: Add one explicit allowlist runner for all 32 proven device-free Phone
  suites. It covers source/static contracts, C++ fixtures, Java compilation,
  JavaScript syntax and mocks, packaging fixtures, release/16-KiB checks, and
  the mock-ADB deployment/benchmark harnesses. The real device and real
  graphics-benchmark scripts are intentionally absent and cannot be discovered
  by wildcard.
- Tests:
  - Pre-integration run of every `phone-*-test.sh` and contract script except
    the two real device runners: **passed**.
  - `android/tests/serverless-hub-fixture-test.sh`: **passed** (136 entities,
    schema and referenced scripts valid).
  - `android/tests/phone-static-regression-test.sh`: **passed**, all 32
    allowlisted suites; nested host regression passed 174/174 checks.
  - `git diff --check`: **passed**, both directly and as the final aggregate
    gate step.
- Known risks and deferred audit: The tablet still uses a symmetric 25 Qt
  logical-pixel safety inset. Real asymmetric Android cutout/rounded-corner
  insets are not transported from Java to the Qt tablet presenter. Guessing
  them from display size was rejected; a future Java→JNI→presenter contract
  needs device validation. Current resize, portrait-transition fallback, and
  minimum-size guards remain covered.
- Real-device validation still required: **not executed**. Besides the full
  device checklist below, exercise left/right landscape rotations on flat,
  notched, hole-punch, waterfall, and rounded-corner displays; verify all
  tablet edges and close controls remain reachable and no content lies under a
  cutout or transient system bar.

## 05 — Native touch Emote

- Branch: `nightly/android-phone-05-emote-audit`
- Commit: `c08094f66c` — `Add native Android phone Emote app`
- Change: Add a Phone-only native QML Emote grid and lifecycle-owned script.
  Requests are namespaced and allowlisted, unavailable resources fail safely,
  timers and avatar overrides are cleaned up deterministically, and the app has
  no Web surface, controller mapping, or mutable QML button-proxy dependency.
  More remains disabled because it downloads remote metadata and installs
  third-party scripts; Create remains disabled by its existing isolation gate.
- Tests:
  - `android/tests/phone-tablet-emote-test.sh`: **passed**, 14 source
    contracts, JavaScript syntax, and the lifecycle mock.
  - `android/tests/phone-tablet-emote-lifecycle-mock.js`: **passed** for open,
    ready, invalid request, play, same-action stop, timer cancellation, avatar
    restoration, signal disconnection, and button removal.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, JavaScript syntax checks, and 174/174 host checks.
  - Qt 6 `qmllint` on `PhoneEmote.qml`: **passed** with non-fatal Qt 6
    unqualified-access warnings for Qt 5-compatible delegate context access.
  - `android/tests/phone-script-payload-test.sh`: **passed** again after the
    new assets became tracked; all required defaults and payload exclusions
    remain consistent.
  - `git diff --check`: **passed**.
- Known risks: Animation availability and visual behavior depend on runtime
  resource loading. Playback deliberately uses a finite timer for every emote,
  including Sit, instead of installing the legacy controller mapping.
- Real-device validation still required: **not executed**. Open/close/reopen
  Emote, trigger every action after cold and warm cache, stop an action by
  tapping it again, switch actions rapidly, move during Sit, background and
  foreground during playback, and confirm the avatar always returns to its
  locomotion animation with no stale highlighted state.

## 04 — Background, Back, and IME lifecycle

- Branch: `nightly/android-phone-04-lifecycle-audit`
- Commit: `26bb47059b` — `Harden Android phone lifecycle state`
- Change: Mark Qt Hidden/Suspended states as non-foreground, clear transient
  consumed-Back bookkeeping on Activity pause, and add an Address dialog
  destruction fallback that drops field focus and hides the IME. Existing
  pending-deep-link callbacks remain pause-aware and are not discarded.
- Tests:
  - `android/tests/phone-app-lifecycle-test.sh`: **passed**, 5 lifecycle
    contract checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, JavaScript syntax checks, and 174/174 host checks.
  - `git diff --check`: **passed**.
- Known risks: The shared foreground flag now reflects Qt's documented Hidden
  and Suspended states on every platform. Inactive remains distinct so a
  temporarily unfocused but visible desktop window is not treated as hidden.
- Real-device validation still required: **not executed**. While Address and
  Login dialogs respectively have the IME raised, background/foreground the
  app, use physical and gesture Back, reopen each dialog, and verify no stale
  key-up, keyboard, focus, or touch capture remains. Repeat while a deep link
  arrives during cold startup and while the app is paused.

## 02 — Fail-closed Phone General Settings

- Branch: `nightly/android-phone-02-settings-contract`
- Commit: `d3752d70a8` — `Remove VR-only phone preferences`
- Change: Replace the inherited broad General Settings list with an explicit
  phone allowlist: Phone Navigation, touch-look sensitivity, and Privacy. This
  removes categories whose complete shared contract still contains desktop
  toolbar/tablet, desktop filesystem, HMD, VR laser/keyboard, or Oculus-only
  behavior. Desktop and VR category selection is unchanged.
- Tests:
  - `android/tests/phone-tablet-general-preferences-test.sh`: **passed**,
    7 contract checks.
  - `(cd android && ./tests/phone-tablet-static-test.sh)`: **passed**,
    including all tablet suites, JavaScript syntax checks, and 174/174 host
    regression checks.
  - `./android/tests/phone-tablet-static-test.sh` from the repository root:
    **failed** in the pre-existing modern-API test because three inputs are
    resolved relative to the caller. The same gate passes from its documented
    Android working directory; the CWD defect is queued as the next task.
  - QML lint: **not executed**; `qmllint` is not installed on this host. The
    selector syntax is covered by source-contract checks.
  - `git diff --check`: **passed**.
- Known risks: Touch-look sensitivity is retained because its yaw/pitch values
  are consumed by the shared avatar drive path. Privacy actions still require
  runtime confirmation of their Android integrations.
- Real-device validation still required: **not executed**. Confirm all three
  retained sections render, scroll, save/cancel correctly, and that pinch and
  X/Y sensitivity changes affect touch navigation after restart. Confirm each
  Privacy toggle has the expected Android behavior.

## 03 — Working-directory-independent static gate

- Branch: `nightly/android-phone-03-static-gate-cwd`
- Commit: `e54fd21d48` — `Fix modern Android test working directory`
- Change: Resolve all remaining Modern Android API test inputs from its
  normalized repository root. This makes the test itself and the aggregate
  tablet static gate independent of the caller's working directory.
- Tests:
  - `android/tests/phone-modern-android-api-test.sh`: **passed**, 15 checks.
  - `android/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, JavaScript syntax checks, and 174/174 host checks.
  - Absolute aggregate-gate invocation from `/tmp`: **passed** with the same
    complete result.
  - `git diff --check`: **passed**.
- Known risks: None in runtime code; this changes only source-test paths.
- Real-device validation still required: **not required for this test-only
  change; not executed**.

## 12 — Cumulative hand-off and remaining boundaries

- Branch: `nightly/android-phone-12-nightly-handoff`
- Commit: `Document Android phone nightly hand-off` (this task's commit)
- Change: Record the exact chained history, consolidate the device-free audit,
  and distinguish hardware/toolchain validation from product work that was
  deliberately not guessed into the Phone client.
- Tests:
  - Every commit recorded below is verified as a descendant of
    `origin/feature/android-phone-support`.
  - `android/tests/phone-static-regression-test.sh`: **passed** on the parent
    runtime commit, all 34 explicitly device-free suites; nested host
    regression passed 174/174 checks.
  - `./android/build-phone.sh doctor`: **passed** on this host, with all
    required tools found and no warnings.
  - Documentation consistency: **passed** (11 exact parent commits and 12 task
    sections); `git diff --check`: **passed**.
- Known risks: This section does not turn static contracts into runtime
  evidence. No APK was produced because the dedicated Phone Qt/non-Qt 16-KiB
  dependency outputs and their verified readiness sentinel are absent.
- Real-device validation still required: **not executed**; use the prioritized
  checklist below.

### Exact branch and commit chain

All branches form one linear chain starting at
`origin/feature/android-phone-support` (`200b46bd60`):

1. `nightly/android-phone-01-host-test-cwd` — `96af2c70b4`
2. `nightly/android-phone-02-settings-contract` — `d3752d70a8`
3. `nightly/android-phone-03-static-gate-cwd` — `e54fd21d48`
4. `nightly/android-phone-04-lifecycle-audit` — `26bb47059b`
5. `nightly/android-phone-05-emote-audit` — `c08094f66c`
6. `nightly/android-phone-06-complete-static-gate` — `ff856ab078`
7. `nightly/android-phone-07-packaging-audit` — `890816d373`
8. `nightly/android-phone-08-error-path-audit` — `5d62ce29de`
9. `nightly/android-phone-09-doctor-output` — `86f4ad08cb`
10. `nightly/android-phone-10-deep-link-audit` — `c513546a1e`
11. `nightly/android-phone-11-settings-privacy` — `af9e84f984`
12. `nightly/android-phone-12-nightly-handoff` — this documentation commit

### Device-free audit disposition

- Settings is fail-closed to the two fully meaningful categories. The shared
  Privacy page was ultimately removed because Phone disables Breakpad and uses
  the Android Discord no-op; this supersedes task 02's provisional retention.
- Login, Address, Back, IME, foreground/background, pending deep links, Audio,
  Menu, Shield, People, Avatar, Places, Home, Tutorial, and Emote now have
  explicit source contracts or lifecycle mocks in the aggregate gate.
- Emote is implemented as packaged native QML with a local animation allowlist.
  It no longer depends on the legacy Web or controller surface.
- More/Community remains disabled. Its contract downloads remote metadata and
  installs third-party scripts, so enabling it requires a product trust policy,
  provenance/signature decisions, and a separately reviewable sandbox design.
- Create remains disabled. Its current implementation owns desktop windows,
  controller mappings, overlay windows, entity-click capture, camera state, and
  renderer state. A safe port first needs a touch-owned selection model and
  screen-space dialog lifecycle; wrapping the existing script would be a large
  untestable integration.
- The Pico WebView bridge was not generalized. Phone's enabled applications
  are local QML and introducing a second embedded-Web lifecycle would add an
  unused remote-content attack surface without a complete Phone consumer.
- The symmetric 25-logical-pixel tablet safety inset remains. Accurate
  asymmetric cutout and rounded-corner geometry requires Android WindowInsets
  transport through Java/JNI into the Qt presenter and must be calibrated on
  multiple display shapes; inferring it from resolution or DPI was rejected.
- No disconnect-on-background policy was added. Android pause is transient and
  forcibly disconnecting would change session semantics; the correct policy
  needs product requirements plus device testing of audio, networking, process
  eviction, and reconnect behavior.
- Packaging is fail-closed for dependency readiness, required APK runtimes,
  backup/transfer denial, ZIP padding, and 16-KiB ELF alignment. A real build is
  still blocked by the absent dedicated dependency artifacts, not by a source
  or host-tool failure.

### Prioritized real-device checklist

1. On one Adreno and one Mali phone, perform clean install/cold launch on an
   API 26–29 device and an API 30+ device; cover microphone accept and deny,
   native-library loading, TLS, and a neutral `overte:` deep link.
2. Exercise login success, invalid credentials, cancellation, gesture/physical
   Back, IME resize, background/foreground, and focus release against both a
   metaverse account and a domain login.
3. Verify landscape orientations on flat, notched, hole-punch, waterfall, and
   rounded displays: tablet edges, close button, portrait-sized transition,
   DPI scaling, system-bar reveal, keyboard, and all retained Settings fields.
4. Connect to live domains and repeat tablet open/app/Home/close cycles for
   Audio, Menu, Shield, People, Avatar, Places, Home, Tutorial, and Emote;
   confirm no world-control touch-through and no stale signal/timer state.
5. Stress Emote play/stop/switch, movement interruption, cache-cold animation
   loading, and background/foreground; the avatar must always regain normal
   locomotion.
6. Validate Audio input/output devices, mute, push-to-talk, sliders, People
   levels/actions, Places slow/offline/federated responses, Avatar bookmarks
   and wearables, and reconnect after network loss or process backgrounding.
7. Run the 16-KiB APK/ELF gate on the produced release artifact, inspect only
   PID-filtered aggregate diagnostics, and sustain the graphics benchmark long
   enough to assess frame pacing, memory, temperature, and battery without
   retaining identifiers or raw logs.
