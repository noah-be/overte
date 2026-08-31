# Android phone nightly work

This file records the cumulative Android phone work based on
`origin/feature/android-phone-support`. Most validation is device-free; any
real-device test is identified explicitly and never implied by a host check.

## 143 — Rebuild and republish the reproducible dependency graph

- Branch: `refactor/android-platform-boundaries`
- Change: Rebuild the complete Phone graph with the reproducible Qt recipe,
  bounded four-job producer profiles, and a 16 GB decimal cgroup ceiling. The
  clean-room test found that the historical v2 libnode recipe revision was
  removed after restore, which discarded the corrected 16 KiB binary and made
  Conan fall back to Pico's 4 KiB package. v3 removes any stale v2 copy before
  restoring the corrected package and verifies the complete graph afterward.
- Local artifact: `android-phone-16k-conan.tgz`, 1,476,694,358 bytes, SHA-256
  `092fde910f2dcc3eb0c2d6cff819f2e6264de4e176750ed1f7625a9a21e926be`.
- Clean-room evidence: An isolated Conan cache was populated with the immutable
  Pico restore first, proving that only the colliding 4 KiB libnode package was
  initially available. The local v3 download then passed its checksum, both
  offline `--build=never` installs, every 16 KiB ELF gate, and the content-bound
  readiness sentinel without a source-build fallback.
- APK evidence: The debug APK built at source revision
  `a4ac144c1d79908968114650b04cf3891ec2754a`; the independent package verifier
  accepted its signature, exact metadata and permissions, arm64-only contents,
  16 KiB ELF/ZIP layout, and embedded source revision.
- Release: [`android-phone-16k-deps-v3`](https://github.com/noah-be/overte/releases/tag/android-phone-16k-deps-v3).
- Historical v1 and v2 releases remain immutable evidence. New consumers must
  use v3.

## 142 — Publish and clean-room-test the complete dependency restore

- Branch: `nightly/android-phone-142-published-dependency-release`
- Commit: `Complete Phone prebuilt dependency restore` (this task's commit)
- Change: Publish the first Phone archive, then test it from an empty Conan
  cache in an Ubuntu 24.04 OCI container. That test exposed two hidden host
  cache dependencies: Pico's download helper entered its source-producing
  `--build=missing` phase, and the v1 Phone archive contained Qt rather than the
  complete Conan graph. Remove the Pico release download from the Phone path,
  pin the build-context profile used by source-free consumers, and export the
  exact complete Phone graph for the corrected v2 release. Pico's own download
  behavior and artifacts remain unchanged.
- Tests:
  - Public v1 asset and checksum download: **passed**.
  - Initial empty-cache container restore: **failed as designed by the audit**;
    source compilation began after the Pico restore and was stopped.
  - Restore-only empty-cache container retry: **failed closed** after checksum
    and cache restore because v1 lacked the remaining binary graph; no source
    fallback occurred.
  - Corrected v2 local artifact in an empty Ubuntu 24.04 container: **passed**;
    SHA-256, complete cache restore, both offline `--build=never` installs, 16
    KiB checks, and the content-bound sentinel ended with
    `CONTAINER_DOWNLOAD_RESTORE_OK`, with no Pico download or source build.
  - Public v2 download in a new empty Ubuntu 24.04 container: **passed**. The
    1,476,660,963-byte release asset matched SHA-256
    `32067b3c16296c77ddd4a84aa91b1e06807511469e3c45e121ca1d53cee67554`;
    the complete restore, both offline installs, all ELF gates, and the sentinel
    ended with `PUBLIC_CONTAINER_DOWNLOAD_RESTORE_OK`. The log contains no Pico
    release URL, `--build=missing`, or source-build phase.
  - Complete device-free regression gate: **passed**, all 41 suites; nested
    host regression passed 332/332. Shell syntax and `git diff --check` passed.
- Release: [`android-phone-16k-deps-v2`](https://github.com/noah-be/overte/releases/tag/android-phone-16k-deps-v2)
  is tied to tag commit `9d24893a73d1d6e9a79e6a0961477e47f111af14` and contains only the
  Phone graph plus its checksum manifest.
- Known risks: The v1 release remains immutable historical evidence but is not
  a complete clean-machine dependency set. Developers must use v2.
- Real-device validation still required: None for archive transport. Build an
  APK from a clean restored graph and rerun unattended hardware smoke when the
  dependency recipe/profile set changes.

## Next possible improvements

These are intentionally handed to later sessions; download/restore completion
is tracked in task 142 rather than repeated here.

1. Add touch-owned Create selection/editing and import UI in small closed
   increments, building on the safe Android archive extraction prerequisite.
2. Exercise login/IME/dialog focus, Back, audio and microphone routing, People,
   Places, Avatar, Emote, Menu, and Shield interactively across success and
   error paths.
3. Validate portrait, rotation, cutouts, safe insets, DPI, and more GPU/device
   families; correct only reproducible layout or rendering defects.
4. Test offline/online recovery, Wi-Fi/mobile switching, disconnect/reconnect,
   and long background/foreground transitions.
5. Run a 30–60 minute populated-domain soak covering thermal behavior, battery,
   audio, networking, and touch responsiveness.
6. Complete release APK/AAB signing and Play upload validation, including the
   final 16-KiB packaging path.
7. Investigate a narrow shared Phone/Pico WebView bridge abstraction for More
   and Community without importing Pico-specific UI or creating an untested
   large integration.

## 141 — Give Phone the Pico-style prebuilt dependency commands

- Branch: `nightly/android-phone-141-prebuilt-download-parity`
- Commit: `Add Pico-style Phone dependency commands` (this task's commit)
- Change: Add `build-phone.sh deps --download` as the normal source-free path,
  restoring the exact published/checksummed shared Android assets first and the
  pinned Phone 16-KiB Qt delta second. Add the matching slow `deps` producer
  fallback, make `setup` mirror Pico's doctor/dependency/prepare/build flow,
  reject unknown dependency/setup options, and document why the historically
  named Pico release is a reusable Android base rather than a VR dependency.
- Tests:
  - `android/phone/tests/phone-build-download-parity-test.sh`: **passed**; verified
    exact shared-then-Phone download ordering, exact slow producer ordering,
    and fail-closed unsupported option handling with local mocks.
  - Existing source-free Phone artifact export and local download/restore from
    task 137 remain **passed** for the exact committed checksum. Network release
    download was **not executed** because this session may not create a release
    and the Phone asset has not yet been published by an authorized maintainer.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 332/332 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 41
    explicitly device-free suites; nested host regression passed 332/332.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: `pico4-deps-v1` is an existing public release, but
  `android-phone-16k-deps-v1/android-phone-16k-conan.tgz` still needs its one
  authorized GitHub release upload. Until then the normal command intentionally
  fails closed rather than compiling Qt silently.
- Real-device validation still required: None for dependency transport; rebuild
  and smoke an APK on hardware after restoring on a clean development machine.

## 140 — Enable bounded Android archive extraction for future Create work

- Branch: `nightly/android-phone-140-safe-android-archive-extraction`
- Commit: `Enable safe Android archive extraction` (this task's commit)
- Change: Remove the obsolete Android empty-result stub now that QuaZip is in
  the proven Android dependency graph. Validate ZIP entries before extraction
  using the same read-only file handle; reject absolute, non-canonical,
  backslash, duplicate, overlong, and symbolic-link paths and cap entries,
  individual size, and aggregate expanded size. Remove partial output after a
  failed extraction. This supplies one safe Create/model-import prerequisite
  without enabling the desktop-oriented Create surface.
- Tests:
  - Incremental real j16 Phone APK build: **passed**; Android compilation and
    link prove the QuaZip headers/library are available, then all 106 native
    libraries/378 LOAD segments and APK content/metadata/ZIP gates passed.
  - `android/phone/tests/phone-archive-extraction-test.sh`: **passed** for the
    fail-closed source contract and removal of the obsolete Android stub.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 40
    explicitly device-free suites; nested host regression passed 330/330.
  - Physical Phone post-link smoke: **passed**; installed-byte verification,
    launch, deep link, three lifecycle cycles, Back recovery, and all crash/page
    mismatch counters passed. A follow-up non-mutating 60-second observation
    kept the process alive for 12/12 samples with zero fatal signatures and
    deliberately left the app running.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The extraction API has no dedicated interactive Phone UI yet;
  archive limits intentionally reject unusually large model bundles. QuaZip's
  actual Android extraction path is compiled and linked but not invoked by the
  current disabled Create surface.
- Real-device validation still required: Once a touch-owned import UI exists,
  import a small valid model archive and confirm malformed, oversized,
  traversal, duplicate, and symlink archives fail without output escaping the
  app's temporary directory.

## 139 — Complete an unattended physical-Phone thermal soak

- Branch: `nightly/android-phone-139-device-thermal-soak`
- Commit: `Document Phone thermal soak validation` (this task's commit)
- Change: Record the first extended current-chain physical-Phone run and the
  accompanying native-runtime closure audit. The audit found every one of the
  106 packaged native libraries reachable from the client or an explicitly
  loaded Qt plugin/QML root, so no speculative packaging removal was made.
- Tests:
  - Physical Phone five-minute graphics/thermal benchmark: **passed** with a
    stable process and required final force-stop; 30 thermal samples peaked at
    status 1 and no crash record or crash-log match was added.
  - Native telemetry: **passed** at 29.74 FPS against a 30-FPS target, 10.89 ms
    GPU time, and 6.12 ms batch time. Framebuffer recreation deltas were zero,
    GL buffer enqueue/cleanup deltas matched, and pending transfer memory was
    zero. Overlay-cache hit rate reached 97.64% after warm-up.
  - Native `DT_NEEDED`/explicit-runtime closure audit: **passed**, 106/106
    packaged libraries reachable and zero orphan candidates.
- Known risks: Five minutes is sufficient for a short stability regression but
  not a battery, sustained-load, network-roaming, or multi-hour thermal test.
  Android `gfxinfo` framestats remained unavailable, as in task 138.
- Real-device validation still required: Repeat for 30–60 minutes in an actual
  populated domain while observing battery drain, thermal throttling, audio,
  network transitions, and interactive visual/touch correctness.

## 138 — Validate the current Phone APK on physical hardware

- Branch: `nightly/android-phone-138-device-smoke-validation`
- Commit: `Validate Phone APK build and device smoke` (this task's commit)
- Change: Make Phone preparation select Draco only when its Conan metadata and
  first archive object both prove an Android ARM64 target, reject explicit host
  packages before staging, and extend the APK's fail-closed native payload
  contract to cover the linked Overte and Qt shared-library graph that
  `bundled_in_lib` does not describe. Add architecture and package fixtures.
- Tests:
  - Real j16 debug APK build: **passed**. All dependency gates passed; the APK
    contains 106 inspected native libraries with 378 ELF LOAD segments, all
    aligned to 0x4000, followed by successful manifest, content, ZIP-alignment,
    and package-integrity gates.
  - Physical Phone unattended smoke: **passed**. Installed bytes matched the
    requested APK; automatic permission grant, launch, neutral local deep link,
    three background/foreground cycles, Back-to-background, and recovery all
    completed with zero crash-log, exit-crash, or page-size mismatch matches.
  - Physical Phone 30-second graphics benchmark: **passed** with required final
    force-stop. The process remained stable, no crash record was added, six
    thermal samples peaked at status 1, and native telemetry measured 29.82 FPS
    against the 30-FPS target. Android `gfxinfo` framestats were unavailable;
    native render telemetry remained valid (13.16 ms GPU, 6.69 ms batch).
  - `android/phone/tests/phone-prepare-architecture-test.sh`: **passed**, including
    selection of Android ARM64 over a host package and explicit-host rejection.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 329/329 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 39
    explicitly device-free suites; nested host regression passed 329/329.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The physical run provides no human assessment of touch feel,
  visual correctness, audio quality, IME behavior, or login flows. Android's
  generic `gfxinfo` path reported no valid frames for this Qt/OpenGL workload,
  so the benchmark relies on the client's purpose-built native telemetry.
- Real-device validation still required: Interactive portrait/landscape and
  cutout inspection, touch/IME dialogs, login and account errors, microphone
  and output-route changes, People/Places/Avatar/Emote/Menu/Shield workflows,
  prolonged background/disconnect recovery, and a longer thermal soak.

## 137 — Add the downloadable Phone 16-KiB dependency delta

- Branch: `nightly/android-phone-137-prebuilt-16k-delta`
- Commit: `Add prebuilt Phone 16 KiB dependency flow` (this task's commit)
- Change: Add a source-free pinned-Qt delta exporter, strict one-asset SHA-256
  manifest, download/restore command, offline `--build=never` regeneration,
  full sentinel finalization, `build-phone.sh setup --download` integration,
  public producer/consumer documentation, and device-free failure fixtures.
  The existing shared Pico download supplies Node and the other native packages;
  the Phone archive carries only the different 16-KiB Qt package.
- Tests:
  - `android/phone/tests/phone-prebuilt-16k-deps-test.sh`: **passed** for valid
    restore sequencing, malformed manifests, and checksum mismatch rejection.
  - Real artifact export: **passed**; produced an approximately 743-MiB
    source-free Conan Qt archive plus a versioned SHA-256 manifest.
  - Local end-to-end download/restore using that exact archive: **passed**;
    checksum, Conan restore, both offline generator installs, all dependency
    ELF gates, and content-bound sentinel publication succeeded without a
    source rebuild.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 326/326 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 38
    explicitly device-free suites; nested host regression passed 326/326.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The archive exists only as a local release-ready output because
  this session is prohibited from pushing or creating a GitHub release. The
  default public URL will fail closed until an authorized maintainer publishes
  the exact checksum-matching asset under `android-phone-16k-deps-v1`.
- Real-device validation still required: None for archive transport; build the
  current APK from the restored graph and run the unattended Phone smoke.

## 136 — Make the guarded 16-KiB Qt build portable and complete

- Branch: `nightly/android-phone-136-systemd-service-guard`
- Commit: `Harden guarded Phone Qt packaging` (this task's commit)
- Change: Replace the unsupported systemd scope/wait combination with a
  transient user service, verify finite limits through delegated cgroup
  boundaries, preserve the caller working directory and tool path, and patch
  the pinned Qt Conan recipe only for the duration of a build so compilation
  remains at j16 while its racy package install is serialized.
- Tests:
  - `android/phone/tests/phone-build-resource-guard-test.sh`: **passed**, including
    exact swap/memory boundaries, delegated-cgroup handling, service dispatch,
    j16 profile retention, and the serial-install recipe contract.
  - Real transient systemd service caller-`PATH` check: **passed**.
  - `android/phone/build-phone-qt-16k.sh`: **passed** with j16 compilation and
    serialized install; all 130 packaged libraries and 520 ELF LOAD segments
    passed 0x4000 alignment with zero failures or inspection errors.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The local pinned recipe contains a historical temporary-package
  source that the guarded patch deliberately replaces only during this build;
  publishing a canonical Phone cache artifact remains a separate task.
- Real-device validation still required: None for the dependency build itself;
  the resulting dependencies must still produce a package-gated APK that is
  installed and exercised on a physical Phone.

## 135 — Synchronize the public benchmark contract

- Branch: `nightly/android-phone-135-benchmark-documentation`
- Commit: `Document hardened phone benchmark contract` (this task's commit)
- Change: Update the public Phone build guide for strict physical-device
  selection, bounded runtime, signal/error cleanup, the required successful
  cleanup marker, atomic private reports, and discoverable automatic reports.
- Tests:
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 319/319 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    device-free suites; nested host regression passed 319/319.
  - Markdown scope review and `git diff --check`: **passed**.
- Known risks: Documentation cannot substitute for a current-chain physical
  Phone run; the connected targets in task 134 remain rejected VR identities.
- Real-device validation still required: Follow the updated section only after
  a supported Phone and current gated artifact are available.

## 134 — Record fail-closed connected-device preflight

- Branch: `nightly/android-phone-134-device-preflight-handoff`
- Commit: `Document phone device preflight blockade` (this task's commit)
- Change: Record the read-only, identifier-free preflight performed after the
  user made connected hardware available; no production code changed.
- Tests:
  - Connected-device enumeration: **blocked as intended**; two authorized
    Android targets were present, so implicit single-target selection failed.
  - Aggregate physical-Phone contract preflight: **0 matching Phones**. Both
    targets triggered the conservative Pico/ByteDance identity rejection; no
    serial, property value, model, or device identifier was printed or stored.
    Emulator, excluded-class, ABI, SDK, GLES, and touchscreen failure counts
    were zero.
  - Installation, Activity start, app smoke, and graphics benchmark on connected
    hardware: **not executed**. Running Phone tests on either rejected target
    would violate the Phone-only/Pico-exclusion contract.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    device-free suites; nested host regression passed 319/319.
  - Shell syntax, `git diff --check`, and clean-worktree check: **passed**.
- Known risks: A supported physical Phone was not available despite connected
  Android hardware, and no current-chain APK exists due absent verified 16-KiB
  dependencies.
- Real-device validation still required: Connect exactly one non-Pico physical
  ARM64 touchscreen Phone meeting API 26+/GLES 3.2+, build current-chain APKs,
  then run the prioritized checklist below without weakening target checks.

## 133 — Require final benchmark app cleanup

- Branch: `nightly/android-phone-133-required-benchmark-cleanup`
- Commit: `Require final phone benchmark cleanup` (this task's commit)
- Change: Force-stop the measured Phone app as a required checked phase before
  publishing success, clear exit-cleanup ownership only after it succeeds, and
  record `cleanup_force_stopped=1` in every successful aggregate summary.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; forced final
    cleanup failure emits only the fixed phase error, triggers one best-effort
    retry, and publishes no summary; successful summaries contain the cleanup
    marker and still stop exactly once.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 319/319 checks,
    including required cleanup and summary-marker contracts.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 319/319.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: If both required stop and best-effort retry fail, Android may keep
  the process until transport returns; the run is unambiguously failed and has
  no successful aggregate report.
- Real-device validation still required: Confirm success contains the marker
  and `pidof org.overte.phone` is empty after an unattended current-chain pass.

## 132 — Keep raw-cleanup errors private and best-effort

- Branch: `nightly/android-phone-132-private-raw-cleanup-error`
- Commit: `Keep phone raw cleanup errors private` (this task's commit)
- Change: Suppress raw filesystem diagnostics during exit-time raw-directory
  removal and prevent a cleanup error from replacing the benchmark result.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; a fake remover
    deletes the raw directory but returns a private error, while the benchmark
    remains successful, emits no raw path/detail, and publishes a valid summary.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: A genuine removal failure can leave mode-0700 raw data in `/tmp`;
  cleanup remains best-effort so it cannot falsify the benchmark result.
- Real-device validation still required: None for injected local cleanup error.

## 131 — Seal the three-hour continuation handoff

- Branch: `nightly/android-phone-131-three-hour-handoff`
- Commit: `Document three-hour phone continuation` (this task's commit)
- Change: Audit and seal the cumulative continuation from task 92 through 130:
  19 package/device-smoke hardenings followed by 20 unattended benchmark and
  report-lifecycle improvements, each on its own stacked branch. The exact
  chain below is contiguous from task 1 through this handoff.
- Tests:
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**.
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**.
  - `android/phone/build.sh doctor`: **passed** for host/Android toolchain;
    dependency graph reports **SETUP required** because verified 16-KiB
    dependencies are not prepared.
  - Shell syntax, `git diff --check`, branch ancestry, 1–130 chain continuity,
    and `git fsck --no-dangling --no-reflogs`: **passed**.
  - Real Android device tests: **not executed** for this chain because no APK,
    AAB, or verified 16-KiB dependency sentinel exists in this worktree; an
    installed artifact of unknown provenance would not validate these commits.
- Known risks: Runtime rendering, thermal behavior, vendor property responses,
  IME/touch ergonomics, audio routing, and process lifecycle still require the
  prioritized physical-device matrix below with freshly built artifacts.
- Real-device validation still required: Build current debug/release artifacts,
  pass package gates, then run unattended smoke and benchmark before the manual
  UI/audio matrix. Never treat an older installed APK as current-chain evidence.

## 130 — Exercise explicit Pico benchmark rejection

- Branch: `nightly/android-phone-130-pico-benchmark-rejection`
- Commit: `Test phone benchmark Pico rejection` (this task's commit)
- Change: Parameterize the fake product identity and exercise the conservative
  Pico/ByteDance identity defense independently of generic VR characteristics.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; a Pico identity
    receives the dedicated refusal before graphics reset, log clear, or Activity
    start, while all physical-Phone boundary fixtures remain green.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The identity check is intentionally conservative to prevent
  accidental use of this Phone-only harness on known VR product families.
- Real-device validation still required: None on Pico hardware; do not run this
  Phone benchmark on Pico/VR devices.

## 129 — Exercise every benchmark device boundary

- Branch: `nightly/android-phone-129-device-contract-fixtures`
- Commit: `Test phone benchmark device boundaries` (this task's commit)
- Change: Parameterize the fake Android properties/features and dynamically
  exercise all physical Phone target predicates.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; emulator,
    Watch, x86-only ABI, API 25, GLES below 3.2, and missing touchscreen each
    fail with the fixed contract error before reset, log clear, or Activity
    start; the valid ARM64 Phone fixture remains green.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Vendor property variations on a valid physical device still need
  observation, though the contract uses standard Android properties/features.
- Real-device validation still required: Confirm the intended device passes the
  full predicate and a known non-Phone target is refused.

## 128 — Prove insecure raw setup is removed

- Branch: `nightly/android-phone-128-raw-mode-cleanup`
- Commit: `Test phone raw report cleanup` (this task's commit)
- Change: Add deterministic coverage for permission-hardening failure on the
  private raw-data directory after automatic aggregate allocation.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; forced raw
    chmod failure exposes only the fixed security error and leaves neither a raw
    directory nor an unpublished automatic aggregate directory.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: SIGKILL remains outside shell cleanup guarantees.
- Real-device validation still required: None for deterministic filesystem
  failure behavior.

## 127 — Clean up insecure automatic report setup

- Branch: `nightly/android-phone-127-report-mode-cleanup`
- Commit: `Clean up phone report mode failures` (this task's commit)
- Change: Install aggregate-report ownership cleanup immediately after path
  allocation, before directory creation and mode hardening.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; forced chmod
    failure on an automatic report emits only the fixed security error, exposes
    no generated path, and leaves no new report directory.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: A hostile privileged process can always interfere with `/tmp`;
  allocation is private and every normal shell exit now removes failed setup.
- Real-device validation still required: None for local chmod failure handling.

## 126 — Remove failed automatic report directories

- Branch: `nightly/android-phone-126-failed-temp-report-cleanup`
- Commit: `Clean up failed temporary phone reports` (this task's commit)
- Change: Install exit cleanup before raw-report allocation and retain an
  automatically allocated aggregate directory only after its summary was
  atomically published. Explicit caller-owned report directories are preserved.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; an automatic
    report followed by forced Activity-start failure leaves no newly created
    report directory, while successful automatic reports remain discoverable.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: SIGKILL during the very short setup/publish window can bypass
  cleanup; no complete `summary.txt` is published before atomic rename.
- Real-device validation still required: None for local ownership semantics;
  ordinary automatic-report collection remains outstanding.

## 125 — Keep automatic benchmark reports discoverable

- Branch: `nightly/android-phone-125-discoverable-temp-report`
- Commit: `Keep temporary phone reports discoverable` (this task's commit)
- Change: Continue hiding caller-selected report paths, but print the generated
  non-personal `/tmp/overte-phone-graphics-report.*` summary location when no
  report directory was requested, so the successful result is usable.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; an automatic
    report prints a strictly shaped `/tmp` summary path whose schema is valid,
    while an explicit private directory still emits only the fixed message.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Automatically generated aggregate reports persist until the
  caller removes them; they contain aggregate metrics only and mode 0600.
- Real-device validation still required: Run once with and once without an
  explicit report directory and confirm both completion messages.

## 124 — Remove interrupted summary temporaries

- Branch: `nightly/android-phone-124-partial-summary-cleanup`
- Commit: `Clean up partial phone benchmark summaries` (this task's commit)
- Change: Track the hidden aggregate-summary temporary in the central exit
  cleanup until its atomic rename succeeds.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; TERM injected
    during temporary-summary permission hardening returns 143, force-stops the
    app exactly once, publishes no summary, and leaves no hidden partial file.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: SIGKILL can bypass shell cleanup, but any remnant remains a
  private hidden temporary and is never mistaken for `summary.txt`.
- Real-device validation still required: None for local temporary cleanup;
  current-chain aggregate collection remains outstanding.

## 123 — Label frame-statistics transport failure

- Branch: `nightly/android-phone-123-benchmark-framestats-error`
- Commit: `Label phone benchmark framestats failure` (this task's commit)
- Change: Treat the required `gfxinfo framestats` capture as a named checked
  ADB phase instead of allowing an unlabeled shell exit.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; forced private
    framestats transport failure exposes only the fixed phase error, performs
    exactly one app cleanup, and publishes no aggregate summary.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Structurally unsupported but successfully returned framestats
  remain represented by `framestats_valid=0`, not a transport failure.
- Real-device validation still required: Confirm the current Android version's
  `gfxinfo framestats` command succeeds for the current-chain package.

## 122 — Exercise benchmark interrupt cleanup

- Branch: `nightly/android-phone-122-benchmark-interrupt-test`
- Commit: `Test phone benchmark interrupt cleanup` (this task's commit)
- Change: Generalize the signal-injecting fake sleeper and exercise INT during
  active sampling in addition to the existing TERM case.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; INT produces
    status 130, exactly one Phone force-stop, and no partial summary; TERM still
    produces status 143 with the same cleanup guarantees.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: SIGKILL remains inherently untrappable.
- Real-device validation still required: Interrupt a current-chain benchmark
  from its controlling process and confirm the app is no longer running.

## 121 — Exercise benchmark signal cleanup

- Branch: `nightly/android-phone-121-benchmark-signal-test`
- Commit: `Test phone benchmark signal cleanup` (this task's commit)
- Change: Add a deterministic fake sleeper that delivers TERM during the
  sampling window and exercises the real benchmark traps end to end.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; TERM produces
    status 143, performs exactly one Phone force-stop, and publishes no partial
    aggregate summary, while every prior benchmark fixture remains green.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: SIGKILL cannot run process cleanup by operating-system design;
  the shared device-lock cooldown still protects immediately following work.
- Real-device validation still required: Interrupt one current-chain benchmark
  with TERM and confirm the package is stopped without retaining raw output.

## 120 — Bound unattended benchmark runtime

- Branch: `nightly/android-phone-120-bounded-benchmark-runtime`
- Commit: `Bound phone benchmark runtime` (this task's commit)
- Change: Limit a single unattended graphics benchmark to 1–3600 seconds and
  its thermal sampling interval to 1–300 seconds, with digit-length checks that
  prevent shell arithmetic overflow before device access.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; 3601-second
    duration and 301-second interval fixtures fail immediately with exact errors
    while all valid aggregate scenarios remain green.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 317/317 checks,
    including explicit duration and sampling bounds.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 317/317.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Longer endurance studies require multiple explicitly scheduled
  bounded passes and appropriate human thermal supervision.
- Real-device validation still required: Verify selected durations and sample
  cadence on the current-chain build; no input is required during a pass.

## 119 — Label benchmark start-phase failures

- Branch: `nightly/android-phone-119-benchmark-phase-errors`
- Commit: `Label phone benchmark start failures` (this task's commit)
- Change: Route required graphics-counter reset and Phone Activity start calls
  through a checked ADB helper with fixed, phase-specific errors.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; deliberately
    private reset/start failures expose only their fixed phase messages, reset
    failure never starts the app, and failed start never triggers cleanup for an
    app the harness did not successfully start.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 315/315 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 315/315.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Optional log clearing remains best-effort by design; required
  collection phases are evaluated separately.
- Real-device validation still required: Observe fixed errors only if either
  required phase fails on the intended current-chain Phone test.

## 118 — Gate benchmark targets to physical Phones

- Branch: `nightly/android-phone-118-benchmark-device-contract`
- Commit: `Gate phone benchmark device contract` (this task's commit)
- Change: Require the explicitly selected benchmark target to be a physical,
  non-Watch/TV/Automotive/VR ARM64 touchscreen with Android API 26+ and OpenGL
  ES 3.2+, matching the packaged Phone runtime contract.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; a fake emulator
    is rejected with the fixed contract error before graphics reset, log clear,
    or Activity start, while the valid physical-Phone fixture remains green.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 315/315 checks,
    including explicit emulator, ABI, touchscreen, SDK, and GLES contracts.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 315/315.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Manufacturer/brand checks remain as an additional conservative
  Pico defense; no identity value is persisted or printed.
- Real-device validation still required: Confirm the intended device passes all
  queried properties and features without retaining their values.

## 117 — Always clean up the benchmarked app

- Branch: `nightly/android-phone-117-benchmark-cleanup`
- Commit: `Clean up phone benchmark lifecycle` (this task's commit)
- Change: Track a successfully started Phone package and force-stop it from a
  best-effort exit cleanup on success and every later error. INT and TERM now
  convert to terminating status codes while still passing through cleanup.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; fake-ADB logs
    prove exactly one cleanup force-stop after a successful benchmark and after
    a deliberately late summary-publication failure.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 310/310 checks,
    including source contracts for cleanup plus INT/TERM termination.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 310/310.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Cleanup is deliberately best-effort so an unavailable transport
  cannot replace the benchmark's actual result.
- Real-device validation still required: Confirm the current-chain Phone
  process is absent after both a successful run and an interrupted run.

## 116 — Keep benchmark publication private and atomic

- Branch: `nightly/android-phone-116-private-benchmark-publish`
- Commit: `Harden phone benchmark summary publication` (this task's commit)
- Change: Give final summary allocation, permission, write, and atomic-publish
  failures fixed errors; remove partial temporary summaries; and stop printing
  the caller's report path on successful completion.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; forced summary
    allocation failure exposes neither fake-tool diagnostics nor the private
    report path and leaves no published summary, while success emits only the
    fixed completion message.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 307/307 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 307/307.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The final filesystem can still fail between phases; each checked
  phase now fails closed and performs best-effort temporary cleanup.
- Real-device validation still required: Run aggregate collection for a
  current-chain APK and confirm the fixed completion message and private report.

## 115 — Keep benchmark setup failures private

- Branch: `nightly/android-phone-115-private-benchmark-setup`
- Commit: `Keep phone benchmark setup errors private` (this task's commit)
- Change: Replace raw `realpath`, `mktemp`, `mkdir`, and `chmod` diagnostics
  during aggregate/raw report setup with fixed phase messages.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; using a
    deliberately private regular file as the requested report directory emits
    only the fixed creation error, leaks no fixture path, and performs no
    mutating ADB operation.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 307/307 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 307/307.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Failures while publishing the final aggregate summary are
  hardened separately from setup failures.
- Real-device validation still required: None for deterministic filesystem
  errors; ordinary current-chain benchmark validation remains outstanding.

## 114 — Preflight benchmark report targets

- Branch: `nightly/android-phone-114-benchmark-report-preflight`
- Commit: `Preflight phone benchmark report targets` (this task's commit)
- Change: Reject symlinked and other non-regular aggregate-summary targets
  before resetting graphics counters, clearing logs, or starting the Phone app.
  Existing regular summaries remain supported through atomic replacement.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; fake-ADB
    command capture proves both a symlink and a directory at `summary.txt` fail
    before any `gfxinfo` reset, log clear, or Activity start.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 307/307 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 307/307.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: A privileged local process could still race filesystem entries;
  the final same-directory rename does not follow a destination symlink.
- Real-device validation still required: None for local report preflight; normal
  benchmark validation remains required for the current-chain APK.

## 113 — Keep benchmark ADB diagnostics private

- Branch: `nightly/android-phone-113-private-benchmark-adb`
- Commit: `Keep phone benchmark ADB errors private` (this task's commit)
- Change: Suppress raw ADB stderr centrally in the unattended graphics
  benchmark, including device enumeration, so transport failures cannot expose
  a serial, account, private endpoint, or other device detail in console logs.
  Keep the fake-ADB regression isolated from the real shared device lock.
- Tests:
  - `android/phone/tests/phone-graphics-benchmark-test.sh`: **passed**; a complete
    benchmark whose fake ADB emits identifying text on every invocation still
    produces a valid aggregate report and exposes none of that text.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 307/307 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 307/307.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Phase-specific benchmark failures are still intentionally terse;
  debugging must occur locally without copying raw device output into reports.
- Real-device validation still required: Run the benchmark against an installed
  current-chain build and confirm aggregate collection still completes.

## 112 — Prove late summary failures clean up the app

- Branch: `nightly/android-phone-112-late-summary-failure`
- Commit: `Test late phone summary failure cleanup` (this task's commit)
- Change: Make the fake summary writer fail on a selected invocation and prove
  that a post-install write failure remains private, marks the run failed, and
  force-stops the already installed Phone app before exiting.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; the second
    summary append fails after installation, emits only the fixed phase error,
    retains no private path, records failure, and performs exactly one cleanup
    force-stop.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 307/307 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 307/307.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The exit trap's final status append is intentionally best-effort
  when the report filesystem itself has become unwritable.
- Real-device validation still required: None for deterministic writer-failure
  handling; ordinary device smoke validates cleanup against Android.

## 111 — Prove report setup fails privately

- Branch: `nightly/android-phone-111-report-setup-failures`
- Commit: `Test phone report setup failures` (this task's commit)
- Change: Add stateful fake `mktemp` and `chmod` tools to exercise temporary
  report allocation and summary-permission failures independently, including
  deliberately private raw error text.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; both setup
    failures reduce to their fixed phase messages, retain no private path, and
    issue zero ADB commands, while all prior success/failure scenarios remain
    green.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 307/307 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 307/307.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Filesystem disappearance after successful setup is covered by
  checked appends from task 110; an exit-trap write remains best-effort.
- Real-device validation still required: None for Fake-tool failure handling.

## 110 — Keep summary write failures private

- Branch: `nightly/android-phone-110-private-summary-write-errors`
- Commit: `Keep phone summary write errors private` (this task's commit)
- Change: Suppress raw `mktemp`, shell-redirection, `chmod`, and `tee` errors;
  give report creation, security, and update failures fixed phase messages; and
  create/write the initial private summary before selecting a device. Later
  appends share one checked helper, while the exit trap remains best-effort.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, forcing a fake
    `tee` private-path failure before ADB, preserving `test_status=failed`, and
    proving existing/symlink summary rejection is also path-private.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 307/307 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 307/307.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: If the report filesystem fails again while the exit trap writes
  final status, no reliable local channel remains; the trap intentionally avoids
  masking the original failure or exposing the path.
- Real-device validation still required: Run the unattended smoke with a fresh
  private report and accept only summaries ending in `test_status=passed`.

## 109 — Keep APK hash failures private

- Branch: `nightly/android-phone-109-private-apk-hash-errors`
- Commit: `Keep phone APK hash errors private` (this task's commit)
- Change: Suppress raw local `sha256sum` stderr and convert an APK read/race
  failure after path resolution into a fixed phase error. Artifact hashing still
  completes before any ADB query or device mutation.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, with a fake
    hasher that emits a private APK path and fails; output retains neither the
    raw detail nor path, and the ADB command log remains empty.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 306/306 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 306/306.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Local filesystem instability remains a hard preflight failure;
  detailed diagnosis requires a separate intentional local hash invocation.
- Real-device validation still required: None for local hashing; record and
  install the exact digest only after a successful preflight.

## 108 — Keep device preflight paths private

- Branch: `nightly/android-phone-108-private-preflight-paths`
- Commit: `Keep phone device preflight paths private` (this task's commit)
- Change: Replace missing/unresolvable APK and report-directory errors with
  fixed path-neutral messages, suppress `realpath` stderr, and validate the
  report destination before device selection. Invalid local inputs now cause
  zero ADB reads as well as zero device mutations.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, adding missing
    private APK and report path cases, no retained path, and empty ADB command
    logs for both.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 305/305 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 305/305.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Detailed local path diagnosis remains intentionally separate
  from shared unattended test logs.
- Real-device validation still required: None for preflight privacy; normal
  current-APK device smoke remains pending on a buildable artifact.

## 107 — Bound loose QML to declared modules

- Branch: `nightly/android-phone-107-qml-module-boundary`
- Commit: `Gate phone package QML module roots` (this task's commit)
- Change: Derive the reviewed loose-QML roots from `qt_dependencies.xml`,
  require declarations to remain below `qml/`, and reject APK/AAB QML files
  outside those roots. Qt may retain flexible files within a declared module,
  but a new or stale module cannot silently expand the package surface.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, adding undeclared
    QML module fixtures for APK and AAB plus an out-of-root dependency fixture.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 303/303 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 303/303.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Files inside an approved module are content-verified and CRC
  checked but not individually enumerated; Qt module revisions need that
  flexibility while `qmldir` remains mandatory.
- Real-device validation still required: Cold-launch and open every native QML
  tablet app from a clean cache to exercise runtime module resolution.

## 106 — Require cache coverage for managed assets

- Branch: `nightly/android-phone-106-cache-asset-coverage`
- Commit: `Gate phone package cache asset coverage` (this task's commit)
- Change: Require every non-QML APK/AAB asset except `cache_assets.txt` itself
  to appear in the content-bound extraction manifest. Stale or unreachable
  scripts, RCC bundles, and serverless resources can no longer ride alongside
  the reviewed cache payload; loose Qt QML remains an explicit separate class.
- Tests:
  - Gradle/source audit: **passed**, all non-QML Phone staging paths add their
    output through `assetList`; Phone contributes no independent source asset
    directory.
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, adding undeclared
    APK script, APK RCC, and AAB script fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 302/302 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 302/302.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Loose `assets/qml/` modules are governed separately by
  `qt_dependencies.xml` and the generated RCC; they are not cache-extracted.
- Real-device validation still required: Cold-launch the final APK after
  clearing app cache to prove every managed asset extracts successfully.

## 105 — Bound package parser resources

- Branch: `nightly/android-phone-105-package-resource-limits`
- Commit: `Bound phone package parser resources` (this task's commit)
- Change: Reject package files above the classic non-ZIP64 4-GiB range before
  ZIP parsing and reject archives with more than 32,768 central-directory
  entries before per-entry validation. Both limits leave wide headroom over
  the current Phone payload while bounding pathological release inputs.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, adding a sparse
    oversized package and a 32,769-entry archive with limit-specific errors.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 301/301 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 301/301.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Opening ZIP metadata still has work proportional to the bounded
  central directory; the limit intentionally rejects a future ZIP64 package
  until Android compatibility and release policy are reviewed.
- Real-device validation still required: None for parser limits; validate the
  final artifact size and install through the standard smoke.

## 104 — Require canonical archive paths

- Branch: `nightly/android-phone-104-canonical-archive-paths`
- Commit: `Require canonical phone package paths` (this task's commit)
- Change: Extend safe relative-path validation to require the exact canonical
  POSIX spelling and printable non-whitespace characters. Dot aliases, repeated
  separators, backslashes, and control/whitespace names can no longer create
  extractor-dependent aliases or unsafe diagnostics.
- Tests:
  - Source inventory: **passed**, 1,957 relevant Phone/asset paths contain no
    newly forbidden name.
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, adding dot-segment,
    repeated-separator, backslash, and control-character fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 299/299 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 299/299.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Printable Unicode remains valid and case-sensitive, matching
  Android assets; any future cross-platform normalization policy needs review.
- Real-device validation still required: None specific to archive names; run
  the final package/install smoke.

## 103 — Reject unsafe archive entry paths

- Branch: `nightly/android-phone-103-safe-archive-paths`
- Commit: `Gate phone package archive paths` (this task's commit)
- Change: Require every APK/AAB ZIP entry, including optional and metadata
  payload, to be a nonempty relative POSIX path without `..` components before
  any later host extraction. Safety is no longer limited to cache-manifest and
  Qt dependency declarations.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, adding APK relative
    traversal, APK absolute path, and AAB base-module traversal fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 297/297 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 297/297.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Archive names remain case-sensitive as required by Android's
  Linux/ZIP runtime; intentional future normalization needs an explicit policy.
- Real-device validation still required: None for host extraction safety; use
  the standard final artifact smoke.

## 102 — Reject ZIP symbolic links

- Branch: `nightly/android-phone-102-zip-symlink-rejection`
- Commit: `Reject phone package ZIP symlinks` (this task's commit)
- Change: Inspect Unix file-type bits in every APK/AAB central-directory entry
  and reject symbolic links. Phone packaging defines only ordinary files and
  empty directories, so host-dependent link extraction cannot redirect or
  reinterpret an otherwise allowlisted asset or bundle-metadata path.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, with independent APK
    asset and AAB metadata symlink fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 296/296 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 296/296.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: A future intentional link-like resource must use an explicit
  Android-supported representation instead of ZIP host filesystem metadata.
- Real-device validation still required: None for archive type parsing; run
  the normal final artifact install and loader smoke.

## 101 — Verify every packaged ZIP entry

- Branch: `nightly/android-phone-101-complete-zip-integrity`
- Commit: `Verify every phone package ZIP entry` (this task's commit)
- Change: Extend streamed ZIP/CRC verification from required files to every
  non-directory APK/AAB entry, including optional Qt assets and bundle
  metadata. Cache-digest inputs are recognized as already verified to avoid a
  second pass; directory entries carrying file data are rejected.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, adding corrupt
    optional APK asset, corrupt AAB `BUNDLE-METADATA`, and data-bearing
    directory fixtures to the required-entry corruption cases.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 295/295 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 295/295.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Full streaming adds I/O proportional to package size but keeps
  memory bounded and is appropriate for the final release gate.
- Real-device validation still required: Install and launch the exact package
  digest that passed this complete archive-integrity check.

## 100 — Reject data after the ZIP end record

- Branch: `nightly/android-phone-100-trailing-zip-data`
- Commit: `Reject trailing phone APK ZIP data` (this task's commit)
- Change: Parse and cross-check the classic APK ZIP end record against the
  central-directory offset, size, entry count, and legal comment, then reject
  any bytes after its declared end. A package can no longer carry ignored stale
  payload after an otherwise valid archive.
- Tests:
  - `android/phone/tests/phone-apk-padding-test.sh`: **passed**, accepting a legal ZIP
    comment and rejecting a 20-byte post-EOCD payload in addition to both
    internal-padding fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 294/294 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 294/294.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Phone APKs remain classic non-ZIP64 archives by contract; a
  future intentional ZIP64 migration needs explicit end-record support and
  Android tooling validation rather than implicit acceptance.
- Real-device validation still required: Run the final gate after signing and
  install that exact digest, confirming signing did not leave trailing data.

## 99 — Bound padding before the ZIP central directory

- Branch: `nightly/android-phone-99-central-directory-padding`
- Commit: `Gate phone APK central directory padding` (this task's commit)
- Change: Include the gap between the final local file payload and the ZIP
  central directory in the APK's 64-KiB internal-padding limit. Incremental or
  stale bytes can no longer bypass the gate by occupying that final internal
  region rather than a gap between two entries.
- Tests:
  - `android/phone/tests/phone-apk-padding-test.sh`: **passed**, adding an APK with
    128 KiB inserted immediately before its relocated central directory.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 293/293 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 293/293.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Bytes after the ZIP end record are outside the internal-entry
  alignment model; signing and distribution tooling should reject such
  non-canonical release artifacts independently.
- Real-device validation still required: Run `zipalign` and install the final
  gated APK; no device test is specific to the central-directory calculation.

## 98 — Keep Python package-gate errors path-private

- Branch: `nightly/android-phone-98-private-package-errors`
- Commit: `Keep phone package errors path-private` (this task's commit)
- Change: Classify missing input, invalid ZIP/CRC, invalid UTF-8, dependency
  declaration, and ordinary package-contract failures without rendering raw
  Python exceptions that can contain worktree or artifact paths. Apply the same
  input privacy rule to the ZIP-padding gate while preserving safe padding and
  package-content diagnostics.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including missing
    private-path input and corrupt required-entry cases.
  - `android/phone/tests/phone-apk-padding-test.sh`: **passed**, including missing
    private-path and invalid-ZIP cases plus the existing excessive-gap fixture.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 292/292 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 292/292.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Detailed local exception text is intentionally outside shared
  package logs; safe contract errors still identify archive-relative entries.
- Real-device validation still required: None for host diagnostic privacy.

## 97 — Keep ELF-gate failures path-private

- Branch: `nightly/android-phone-97-private-elf-errors`
- Commit: `Keep phone ELF errors path-private` (this task's commit)
- Change: Replace ELF input, extraction, scan-root, and empty-package errors
  with phase-specific path-neutral messages, and suppress raw failing
  `readelf` output that can contain SDK/worktree locations. Relative packaged
  library names remain available for actionable artifact diagnosis.
- Tests:
  - `android/phone/tests/phone-elf-alignment-test.sh`: **passed**, covering a fake
    `readelf` private-path failure plus missing, invalid, and empty package
    inputs without retaining their private paths.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 290/290 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 37
    explicitly device-free suites; nested host regression passed 290/290.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Detailed tool troubleshooting deliberately requires a separate
  intentional local invocation; shared release logs retain safe phase context.
- Real-device validation still required: None for host diagnostic privacy.

## 96 — Enforce the Phone package layout boundary

- Branch: `nightly/android-phone-96-package-layout-boundary`
- Commit: `Gate phone package archive layout` (this task's commit)
- Change: Reject AABs that mix root-level APK payload with the `base` module,
  contain any unreviewed feature-module manifest, or contain module manifests
  without the required `base` module. Phone defines no dynamic features, so
  ignored module payload can no longer hide outside logical package checks.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including explicit
    mixed-layout, unexpected-feature, and missing-base fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 286/286 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 36
    explicitly device-free suites; nested host regression passed 286/286.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: If Phone intentionally gains a dynamic feature, its module must
  receive its own reviewed contents, manifest, code, and native-payload policy
  before the archive boundary can be expanded.
- Real-device validation still required: None for archive classification;
  install the final gated base-only APK through the standard device checklist.

## 95 — Verify required ZIP entry integrity

- Branch: `nightly/android-phone-95-package-entry-integrity`
- Commit: `Verify phone package entry integrity` (this task's commit)
- Change: Stream every required APK/AAB entry not already read by the cache
  digest, forcing ZIP decompression and CRC validation for the manifest, DEX,
  native runtimes, cache manifest, and required loose QML markers. Presence in
  the central directory alone no longer satisfies the package gate.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including APK DEX
    and AAB native-library fixtures corrupted after ZIP creation.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 284/284 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 36
    explicitly device-free suites; nested host regression passed 284/284.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Integrity is checked for required and cache-declared payloads;
  signing still establishes publisher trust and must be validated separately.
- Real-device validation still required: Install and launch a package that
  passed the gate to validate Android/Qt loader behavior on its final bytes.

## 94 — Reject undeclared ARM64 native libraries

- Branch: `nightly/android-phone-94-native-library-allowlist`
- Commit: `Gate phone package native library allowlist` (this task's commit)
- Change: Treat the core Phone runtimes plus the native plugins declared by
  `qt_dependencies.xml` as an exact ARM64 package allowlist. APKs and AABs with
  stale or otherwise undeclared same-ABI `.so` payloads now fail alongside the
  existing foreign-ABI rejection.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including distinct
    APK and AAB fixtures containing an undeclared ARM64 runtime.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 283/283 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 36
    explicitly device-free suites; nested host regression passed 283/283.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Every intentional future native runtime must be reviewed and
  added to the staging/dependency declaration and package contract together.
- Real-device validation still required: Run loader and startup smoke on the
  final APK to prove the exact allowlist retains every runtime-selected plugin.

## 93 — Bound cache-manifest resource use

- Branch: `nightly/android-phone-93-cache-manifest-limits`
- Commit: `Bound phone package cache manifest` (this task's commit)
- Change: Reject package cache manifests larger than 4 MiB, containing more
  than 32,768 asset entries, or containing a UTF-8 path longer than 1,024
  bytes before doing archive-wide presence and digest work. Pathological APK
  or AAB inputs can no longer drive unbounded manifest allocation or iteration.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, with independent
    fixtures proving each limit reports its intended fail-closed error.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 282/282 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 36
    explicitly device-free suites; nested host regression passed 282/282.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: Limits deliberately leave ample growth above the current Phone
  payload. The content-digest pass remains proportional to legitimate packaged
  asset bytes; archive size policy belongs in release infrastructure.
- Real-device validation still required: None for parser resource limits; the
  produced artifacts still require the final package gate and device checklist.

## 92 — Verify packaged cache contents against their digest

- Branch: `nightly/android-phone-92-cache-digest-gate`
- Commit: `Verify phone package cache content digest` (this task's commit)
- Change: Recompute the `cache_assets.txt` SHA-256 from every declared packaged
  asset's sorted UTF-8 path, NUL separator, and streamed bytes for both APK and
  AAB layouts. Reject legacy numeric stamps, unsorted manifests, and packages
  whose assets changed after the manifest was generated.
- Tests:
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including valid APK
    and AAB fixtures plus tampered-asset, legacy-stamp, unsorted, malformed,
    incomplete, duplicate, traversal, ABI, native-runtime, and QML cases.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 279/279 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 36
    explicitly device-free suites; nested host regression passed 279/279.
  - Python/shell syntax and `git diff --check`: **passed**.
- Known risks: This proves package/cache consistency, not publisher identity;
  signing trust and the loader's extraction behavior still need release and
  device validation. Digest verification streams assets to keep memory bounded
  but adds package-gate I/O proportional to the declared cached payload.
- Real-device validation still required: Build the current debug and signed
  release artifacts, record their SHA-256, run the combined package gate, then
  execute the unattended device smoke. No device test is needed for the fixture
  parser itself.

## 91 — Final cumulative hand-off

- Branch: `nightly/android-phone-91-nightly-handoff`
- Commit: `Document final Android phone nightly handoff` (this task's commit)
- Change: Refresh the exact 01–91 linear branch/commit chain, consolidate the
  completed device-free work, preserve rejected/product-blocked boundaries, and
  separate anonymous capability probes and an installed unknown-artifact
  baseline from validation still required on an APK built from this chain.
- Tests:
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 36 explicit
    device-free suites; nested host regression passed 277/277 checks.
  - `./android/phone/build.sh doctor`: **passed**, all host tools found and the
    absent dedicated Phone dependency graph correctly reported `[SETUP]`.
  - Offline Gradle missing-dependency diagnostics: **expected failures passed**;
    the verified and explicit legacy setup errors were actionable and had no
    false `compileSdk` error.
  - Linear ancestry, task-section/branch/commit consistency, shell/Python/JS
    syntax exercised by aggregate suites, and `git diff --check`: **passed**.
  - Branch-tip/parent audit: **passed** for all 90 committed task branches;
    every branch points at its recorded commit and descends from its predecessor.
  - Scope/privacy audit: **passed**, 81 changed Phone/shared files, zero
    Pico-specific paths, and no real serial, private host path/domain, personal
    datum, or retained raw device log; identifier-like values are mock fixtures.
  - Changed-file syntax audit: **passed** for 31 shell, 2 Python, 18 JavaScript,
    and 2 XML files; all 30 documented test paths exist and task sections 01–91
    are unique and complete.
- Device evidence:
  - Installed-artifact baseline with unknown provenance: **passed** for launch,
    one neutral local deep link, five background/foreground cycles, long Back,
    stable process, resumed Phone Qt Activity, zero crash markers, and zero
    page-size mismatch markers. It is not evidence for commits 01–91.
  - Anonymous locked capability probes: **passed** for physical ARM64 touchscreen
    Phone classification, API/OpenGL requirements, epoch log cursor, and
    structured exit-info. No identifier, property value, or raw log was retained.
  - Current-chain APK install/smoke: **not executed**; no APK was buildable because
    the dedicated verified 16-KiB Phone Qt/non-Qt dependency graph is absent.
- Known risks and remaining boundaries: More/Community, Create, Pico WebView
  abstraction, asymmetric WindowInsets transport, signed release/split APKs,
  online account/domain behavior, audio hardware, graphics/thermal performance,
  and OEM lifecycle behavior still require product decisions, external systems,
  a buildable artifact, or representative hardware. No speculative integration
  was added for them.
- Real-device validation still required: Follow the prioritized checklist below
  using a package-gated, digest-recorded APK from this final chain.

## 90 — Label APK analyzer failures without private paths

- Branch: `nightly/android-phone-90-apkanalyzer-errors`
- Commit: `Report phone APK analyzer field failures` (this task's commit)
- Change: Give every merged-manifest query a safe field-specific error while
  retaining suppression of raw analyzer stderr. Java/SDK/tool failures no longer
  exit silently or expose local command-line-tool paths in shared gates.
- Tests:
  - `android/phone/tests/phone-apk-metadata-test.sh`: **passed**; a target-SDK analyzer
    failure containing a synthetic private path becomes only the generic field
    error, alongside all existing metadata fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 277/277 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 277/277 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Detailed analyzer debugging is intentionally a separate local
  invocation outside shared build logs.
- Real-device validation still required: None for host analyzer error handling.

## 89 — Verify version metadata in the final APK

- Branch: `nightly/android-phone-89-apk-version-metadata`
- Commit: `Gate phone APK version metadata` (this task's commit)
- Change: Read final binary-manifest version fields and require a positive
  signed-32-bit `versionCode` plus the same portable 1–100-character
  `versionName` form as the Gradle release gate. Version names are never echoed.
- Tests:
  - `android/phone/tests/phone-apk-metadata-test.sh`: **passed**, adding overflow code
    and unsafe whitespace/slash name failures to existing metadata fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 276/276 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 276/276 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Play monotonicity remains external state and cannot be inferred
  from one artifact; the gate verifies only safe range and representation.
- Real-device validation still required: None specific to version parsing; tie
  later device results to artifact digest and release records.

## 88 — Bind APK debug state to the Gradle variant

- Branch: `nightly/android-phone-88-variant-debuggable-gate`
- Commit: `Gate phone APK debuggable variant state` (this task's commit)
- Change: Let the merged-manifest gate enforce an optional expected debug state,
  and have Gradle pass `1` for debug variants and `0` for release variants. A
  release APK accidentally marked debuggable now fails final packaging checks.
- Tests:
  - `android/phone/tests/phone-apk-metadata-test.sh`: **passed**, covering matching
    debug/release expectations and a release/debug mismatch failure.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 274/274 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 274/274 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Full Gradle packaging remains blocked by absent Phone dependencies;
  executable checker fixtures and static task wiring cover this change.
- Real-device validation still required: Release smoke must set
  `PHONE_EXPECT_DEBUGGABLE=0` and use the same gated artifact digest.

## 87 — Gate merged metadata in every final APK

- Branch: `nightly/android-phone-87-apk-metadata-gate`
- Commit: `Gate phone APK manifest metadata` (this task's commit)
- Change: Add an `apkanalyzer`-based final APK gate for package ID, min/target
  SDK, exact permissions, and boolean debug state, and invoke it from the
  combined contents/ELF/zipalign/padding gate used by Gradle and device smoke.
- Tests:
  - `android/phone/tests/phone-apk-metadata-test.sh`: **passed**, with good metadata
    plus wrong-ID, stale-SDK, extra-permission, and invalid-debug fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 272/272 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 272/272 host checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 36 explicit
    device-free suites.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: AAB metadata remains protobuf/bundletool-specific; its content
  gate is covered separately, while release CI must inspect generated splits.
- Real-device validation still required: None specific to host metadata parsing;
  a current APK must pass this gate before the existing device smoke can run.

## 86 — Guard device package-gate test overrides

- Branch: `nightly/android-phone-86-preflight-override-guard`
- Commit: `Guard phone package preflight overrides` (this task's commit)
- Change: A nonstandard `PHONE_APK_PREFLIGHT` executable now requires explicit
  `PHONE_ALLOW_TEST_OVERRIDES=1`. The device-free Fake-ADB harness opts in;
  normal device runs cannot accidentally inherit a bypassing package checker.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; an unguarded
    override is rejected before every ADB command, then the explicitly guarded
    mock executes all positive and negative flows.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 267/267 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 267/267 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: The explicit override remains powerful by design for isolated
  host tests; release/device automation must never set it.
- Real-device validation still required: Confirm a normal current-APK smoke uses
  the repository gate with no override variables present.

## 85 — Label package exit-diagnostic phases

- Branch: `nightly/android-phone-85-exit-info-phase-errors`
- Commit: `Report phone exit diagnostic phase failures` (this task's commit)
- Change: Check and label baseline and final package exit-info queries
  independently. Both remain identifier-free, but an unavailable or malformed
  response now identifies whether launch baseline or post-lifecycle diagnosis
  failed instead of exiting silently under shell error handling.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; baseline and
    second-query failures emit their respective safe errors, final status is
    failed, and no unverifiable aggregate crash field is written.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 265/265 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 265/265 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Unsupported OEM exit-info output remains an explicit failure;
  review it locally before extending the structural parser.
- Real-device validation still required: Run a current-APK smoke and confirm
  both exit-info phases succeed and remain monotonic.

## 84 — Prove cleanup failure cannot pass

- Branch: `nightly/android-phone-84-cleanup-failure-contract`
- Commit: `Test phone device cleanup failure contract` (this task's commit)
- Change: Extend Fake-ADB with a final-force-stop failure. The real smoke must
  report `test_status=failed`, omit `cleanup_force_stopped=1`, and issue one
  best-effort finalizer retry rather than accepting incomplete cleanup.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, proving two
    failed cleanup attempts after the successful pre-launch force-stop and no
    false success field.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 263/263 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 263/263 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: A disconnected device can prevent both cleanup attempts; the
  failed status then correctly requires operator cleanup after reconnect.
- Real-device validation still required: Simulate a late disconnect only in a
  disposable run and confirm failed status, then manually force-stop on reconnect.

## 83 — Stop the tested app after unattended smoke

- Branch: `nightly/android-phone-83-device-smoke-cleanup`
- Commit: `Clean up phone app after device smoke` (this task's commit)
- Change: Require a final force-stop before a successful result and record
  `cleanup_force_stopped=1`. Any failure after installation performs best-effort
  force-stop in the EXIT finalizer, preventing a crashed test from leaving the
  Phone app foregrounded, network-active, or holding its keep-screen-on flag.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; success and a
    launcher failure both issue pre-launch plus finalizer/required cleanup, while
    only success records the cleanup flag.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 262/262 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 262/262 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Force-stop preserves installed APK/data but ends active network
  sessions; this is intentional test cleanup and is documented.
- Real-device validation still required: Run the current-APK smoke and confirm
  the app is stopped and display wake lock released after success and failure.

## 82 — Give device summaries an explicit final status

- Branch: `nightly/android-phone-82-device-summary-status`
- Commit: `Record final phone device smoke status` (this task's commit)
- Change: Install an EXIT finalizer immediately after private summary creation.
  Every run reaching device/report phases now ends with exactly one explicit
  `test_status=passed` or `test_status=failed`, so incremental lifecycle flags
  cannot be mistaken for a complete pass after a later abort.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; successful flow
    records `passed`, while installed-read and launcher failures record `failed`.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 260/260 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 260/260 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Failures before report creation intentionally produce no summary;
  their local preflight error remains the authoritative result.
- Real-device validation still required: Run both a successful current-APK
  smoke and an intentionally interrupted disposable run; confirm final status.

## 81 — Report installed-APK read failures safely

- Branch: `nightly/android-phone-81-installed-apk-read-failure`
- Commit: `Handle phone installed APK read failures` (this task's commit)
- Change: Check the complete `exec-out cat | sha256sum` provenance pipeline and
  replace transport/path detail with a generic failure. Unreadable installed
  bytes cannot terminate ambiguously or set `installed_apk_verified=1`.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; a synthetic
    private installed path/serial on stderr is suppressed, the safe phase error
    remains, and provenance success is absent.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 258/258 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet/lifecycle/package suites and 258/258 host checks.
  - Shell syntax and `git diff --check`: **passed**.
- Known risks: Restricted OEM package storage now causes an explicit smoke
  failure; provenance is never weakened to accommodate it.
- Real-device validation still required: Run the current-APK smoke and confirm
  installed bytes remain readable and hash-identical on the prepared phone.

## 80 — Label privacy-reduced ADB phase failures

- Branch: `nightly/android-phone-80-adb-phase-errors`
- Commit: `Report phone smoke ADB phase failures` (this task's commit)
- Change: Route install, force-stop, Activity starts, deep-link delivery, Home,
  and Back through a checked phase wrapper. Raw ADB detail remains suppressed,
  while failures now identify the exact safe phase and cannot continue.
- Tests:
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; a launcher-start
    error with a synthetic serial on stderr becomes only `launcher start failed`
    and never records launch success.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 257/257 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; a failed install
    emits a synthetic serial/path on raw stderr, which is absent from captured
    smoke output while the generic error remains.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 255/255 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; foreign/stale/
    extra-permission/mode/package-gate failures each leave the ADB command log
    completely empty.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 253/253 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including a
    package-gate failure rejected before any install command.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 252/252 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, recording debug
    mode and rejecting a debug APK when release mode is required, before install.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 250/250 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including an APK
    with unexpected camera permission rejected before installation.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 248/248 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including a
    targetSdk 35 APK rejected before any install command.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 246/246 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including an
    unrelated application ID rejected with no install command.
  - Local tool capability: **passed**, SDK `apkanalyzer` is available.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 244/244 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including API 25
    rejection before installation.
  - Anonymous locked device runtime probe: **passed**,
    `phone_runtime_contract=1`; no values or identifier were logged.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 241/241 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including a
    qemu target rejected before any install command.
  - Anonymous locked device capability probe: **passed**,
    `supported_physical_phone_contract=1`; no property or identifier was logged.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 239/239 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**; a benign
    verification message records zero, while an incompatible linker-alignment
    message records one and returns the diagnostic failure status 2.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 236/236 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed** with the
    structural response contract and existing transport-failure fixture.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 235/235 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including new
    logcat and exit-info failure fixtures that must abort before success fields.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 233/233 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, exercising the
    cursor command and time-bounded logcat invocation.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 231/231 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, asserting the
    private fixture root is absent from success, digest-mismatch, PID-restart,
    and sticky-foreground output.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 230/230 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-doctor-output-test.sh`: **passed**, with a synthetic
    private path that must not escape the verifier subprocess.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 229/229 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-doctor-output-test.sh`: **passed**, covering setup,
    content-verified ready, stale, and shared-checker failure states.
  - `./android/phone/build.sh doctor`: **passed**, expected `[SETUP]` locally.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 228/228 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-doctor-output-test.sh`: **passed**, covering missing and
    present marker states plus preservation of shared checker failures.
  - `./android/phone/build.sh doctor`: **passed**, reports `[SETUP]` in this
    worktree because dedicated dependencies are absent.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 227/227 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `./android/phone/build.sh doctor`: **passed**, all required host tools.
  - Offline Gradle configuration without the 16-KiB sentinel: **expected
    failure**, solely the documented sentinel error; no `compileSdk` error.
  - Offline Gradle configuration with the legacy migration switch but absent
    legacy dependencies: **expected failure**, solely the documented setup
    error; no `compileSdk` error.
  - `android/phone/tests/phone-release-config-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 225/225 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including both
    new lifecycle failure fixtures.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 35
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
  - `android/phone/tests/phone-data-protection-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 224/224 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-release-config-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 221/221 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**, including the
    new protected symlink fixture.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 220/220 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-device-smoke-mock-test.sh`: **passed**.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, 35 device-free
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
  - `bash -n android/phone/tests/phone-device-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 218/218 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `bash -n android/phone/tests/phone-device-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 215/215 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `bash -n android/phone/tests/phone-device-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 211/211 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including a complete
    synthetic AAB and a missing-runtime AAB failure alongside all APK fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 207/207 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `bash -n android/phone/tests/phone-device-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 204/204 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `bash -n android/phone/tests/phone-device-test.sh`: **passed**.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 202/202 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-script-payload-test.sh`: **passed**, reporting 13/13
    synchronized startup scripts and all payload exclusions.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 200/200 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, with every required
    cached script present in valid fixtures and covered by cache/ZIP checks.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 199/199 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, with corrected
    complete fixtures and an explicit present-in-APK/but-omitted-from-cache case.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 196/196 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including explicit
    duplicate-entry and unexpected-x86_64 fixtures plus all completeness cases.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 194/194 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, with a generated
    omission fixture for every base/declaration runtime including all four new
    entries, plus QML/cache failure fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 192/192 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable successful-response-with-null-data callback and directory/record
    shape contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable missing-response callback and profile-content type contract.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-places-test.sh`: **passed**, covering exact
    limit, timer registration, expiry ownership, callback cancellation, entity
    deletion, and cleanup invocation contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including portal
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
  - `android/phone/tests/phone-tablet-avatar-test.sh`: **passed**, covering shared URL
    validation, both action boundaries, and QML input lengths.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-avatar-test.sh`: **passed**, covering Phone
    omission, shared construction gate, and Desktop/Pico preservation.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-dialog-routing-test.sh`: **passed**, including bounded
    fields, synchronous password clearing, and destruction-fallback clearing.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including the C++
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
  - `android/phone/tests/phone-dialog-routing-test.sh`: **passed**, including maximum
    length, normalization, control-character, local-error, and validated-value
    delegation contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-avatar-test.sh`: **passed**, including scale
    type/finiteness/range, initialized-model, settings-object, and error contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable mock proving invalid names issue no request and `user/name`
    reaches the connection endpoint as `user%2Fname`.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-people-menu-test.sh`: **passed**, including timer
    ownership, replacement cancellation, reference detachment, and execution-
    time Phone-policy contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, covering legacy and
    content-digest markers plus short, non-hex, oversized, non-ASCII, duplicate,
    traversal, missing-asset, native-runtime, and QML-asset failures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 188/188 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, including escape
    helper, metacharacter, and absolute-path-use contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-app-lifecycle-test.sh`: **passed**, including ordered
    background-retention and destroy-cleanup contracts.
  - `android/phone/tests/phone-deep-link-test.sh`: **passed**, 20 JVM assertions.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-app-lifecycle-test.sh`: **passed**, including an
    ordered source contract for initial Down, native decision, repeat ownership,
    matching Up, and pause-state reset.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-quick-goto-test.sh`: **passed**, including an
    executable mock for button registration, valid Home lookup, packaged
    Tutorial, malformed/overlong fallback, and tablet close on every action.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-shield-test.sh`: **passed**, including guarded
    setup/teardown and Desktop/Pico preservation contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-portal-lifecycle-test.sh`: **passed**, including
    JavaScript syntax and an executable invalid/valid preload, repeated-entry,
    unload-cancellation, completed-navigation, and deletion mock.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including the new
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
  - `android/phone/tests/phone-tablet-places-test.sh`: **passed**, including outgoing
    destination and incoming address/finite-position contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-avatar-test.sh`: **passed**, including explicit
    QML, navigation, and manipulation-message boundary contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-people-menu-test.sh`: **passed**, including an
    executable mock for malformed messages, valid open, timer ownership,
    cancellation, repeated lifecycle transitions, and shutdown.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-people-menu-test.sh`: **passed**, including
    explicit contracts for both blocked Settings actions.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-people-menu-test.sh`: **passed**, including
    privacy-boundary and no-direct-personal-log contracts plus the executable
    People lifecycle mock.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-settings-scale-test.sh`: **passed**, 17
    selector, layout, non-construction, and desktop/Pico preservation checks.
  - `android/phone/tests/phone-tablet-app-router-test.sh`: **passed**.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-audio-test.sh`: **passed**, 16 Phone/Desktop/VR
    presentation and lifecycle contracts.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-emote-test.sh`: **passed**, 15 source contracts
    plus the executable lifecycle mock.
  - Lifecycle mock: **passed** for play, same-action stop, surface close,
    timer cancellation, restoration, reopen/play, and script shutdown.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-app-router-test.sh`: **passed**, including
    executable Home, unrelated-app, active-Settings, post-navigation, malformed,
    inherited-property, local-file, and remote-URL cases.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-actionbar-qml-lifetime-test.sh`: **passed**, including
    a new executable mock for deferred-timer cancellation, destroyed-fragment
    geometry, signal teardown, fragment close, and world-control restoration.
  - `android/phone/tests/phone-tablet-routing-test.sh`: **passed**.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-security-test.sh`: **passed**, ten source
    contracts plus an executable Node normalization suite covering empty,
    malformed, mixed-separator, duplicate, and prototype-named entries.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including traversal,
    absolute-path, duplicate-entry, Unicode-digit, and oversized-stamp fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 181/181 checks,
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including twelve
    independently omitted QML-module metadata fixtures in addition to all 25
    native-runtime omissions, the general cached-asset fixture, and three
    malformed/traversing/duplicate declaration fixtures.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 179/179 checks.
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including a fixture
    omitting each of the 25 native entries independently.
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 177/177 checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 34
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
  - `android/phone/tests/phone-host-regression-test.sh`: **passed**, 175/175 checks,
    including a regression rejection for raw parser details in `qWarning`.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-app-router-test.sh`: **passed**, including the
    executable Node lifecycle mock and ten rejected payload classes.
  - `android/phone/tests/phone-tablet-routing-test.sh`: **passed**.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet contracts and 174/174 host checks.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 34
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
  - Before the fix, `./android/phone/tests/phone-host-regression-test.sh`: **failed**,
    173 of 174 checks passed; `awk` could not open
    `phone/apps/phoneInterface/build.gradle` from the repository root.
  - Before the fix, `(cd android && ./tests/phone-host-regression-test.sh)`:
    **passed**, 174 of 174 checks.
  - After the fix, `./android/phone/tests/phone-host-regression-test.sh` from the
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
  - `android/phone/tests/phone-doctor-output-test.sh`: **passed**, including shared
    checker status propagation.
  - `bash -n android/phone/build.sh android/phone/tests/phone-doctor-output-test.sh`:
    **passed**.
  - `./android/phone/build.sh doctor`: **passed**, Phone heading and next step,
    all tools found with no warnings.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 34 suites;
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
  - `android/phone/tests/phone-tablet-general-preferences-test.sh`: passed (10
    contract checks).
  - `android/phone/tests/phone-tablet-static-test.sh`: passed (174 checks plus
    focused tablet suites).
  - `android/phone/tests/phone-static-regression-test.sh`: passed (34 explicitly
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
  - `android/phone/tests/phone-tablet-places-test.sh`: **passed**, 24 checks.
  - `node --check scripts/system/places/places.js`: **passed**.
  - `android/phone/tests/phone-deep-link-test.sh`: **passed**, 20 Java assertions.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 34 suites;
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
  - `android/phone/tests/phone-apk-contents-test.sh`: **passed**, including 9
    independently omitted native-runtime fixtures plus the asset fixture.
  - `python3 -m py_compile android/phone/tests/check-phone-apk-contents.py`:
    **passed**; generated bytecode was removed afterward.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 33 suites;
    nested host regression passed 174/174 checks.
  - `./android/phone/build.sh doctor`: **passed**, all tools found with no
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
  - `android/phone/tests/phone-data-protection-test.sh`: **passed**, all 9 domains in
    all three rule sections.
  - `android/phone/tests/phone-release-config-test.sh`: **passed**.
  - Python bytecode compilation and `xmllint --noout` for both rule files and
    the manifest: **passed**; generated bytecode was removed afterward.
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 33 suites;
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
  - `android/phone/tests/serverless-hub-fixture-test.sh`: **passed** (136 entities,
    schema and referenced scripts valid).
  - `android/phone/tests/phone-static-regression-test.sh`: **passed**, all 32
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
  - `android/phone/tests/phone-tablet-emote-test.sh`: **passed**, 14 source
    contracts, JavaScript syntax, and the lifecycle mock.
  - `android/phone/tests/phone-tablet-emote-lifecycle-mock.js`: **passed** for open,
    ready, invalid request, play, same-action stop, timer cancellation, avatar
    restoration, signal disconnection, and button removal.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
    tablet suites, JavaScript syntax checks, and 174/174 host checks.
  - Qt 6 `qmllint` on `PhoneEmote.qml`: **passed** with non-fatal Qt 6
    unqualified-access warnings for Qt 5-compatible delegate context access.
  - `android/phone/tests/phone-script-payload-test.sh`: **passed** again after the
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
  - `android/phone/tests/phone-app-lifecycle-test.sh`: **passed**, 5 lifecycle
    contract checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-tablet-general-preferences-test.sh`: **passed**,
    7 contract checks.
  - `(cd android && ./tests/phone-tablet-static-test.sh)`: **passed**,
    including all tablet suites, JavaScript syntax checks, and 174/174 host
    regression checks.
  - `./android/phone/tests/phone-tablet-static-test.sh` from the repository root:
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
  - `android/phone/tests/phone-modern-android-api-test.sh`: **passed**, 15 checks.
  - `android/phone/tests/phone-tablet-static-test.sh`: **passed**, including all
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
  - `android/phone/tests/phone-static-regression-test.sh`: **passed** on the parent
    runtime commit, all 34 explicitly device-free suites; nested host
    regression passed 174/174 checks.
  - `./android/phone/build.sh doctor`: **passed** on this host, with all
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
12. `nightly/android-phone-12-nightly-handoff` — `2bbdf69a24`
13. `nightly/android-phone-13-tablet-route-allowlist` — `eb84857640`
14. `nightly/android-phone-14-bookmark-log-privacy` — `6eaff19c18`
15. `nightly/android-phone-15-qml-runtime-gate` — `b06bee5136`
16. `nightly/android-phone-16-qml-asset-gate` — `a14eb575cf`
17. `nightly/android-phone-17-cache-manifest-gate` — `08108aa93c`
18. `nightly/android-phone-18-security-settings` — `adc6e3e3a8`
19. `nightly/android-phone-19-actionbar-lifecycle` — `df4ec29499`
20. `nightly/android-phone-20-settings-message-scope` — `7a40893e8f`
21. `nightly/android-phone-21-emote-close-cleanup` — `378fbcf848`
22. `nightly/android-phone-22-audio-controls` — `bb6d806bf6`
23. `nightly/android-phone-23-graphics-settings` — `03210855fa`
24. `nightly/android-phone-24-people-log-privacy` — `f9798cda44`
25. `nightly/android-phone-25-menu-settings-policy` — `41db95822b`
26. `nightly/android-phone-26-people-message-validation` — `b035dec9de`
27. `nightly/android-phone-27-avatar-message-validation` — `9bea441b3a`
28. `nightly/android-phone-28-places-portal-validation` — `750bc10b03`
29. `nightly/android-phone-29-portal-entity-lifecycle` — `3c6566779e`
30. `nightly/android-phone-30-shield-menu-scope` — `a9bcbea59b`
31. `nightly/android-phone-31-quick-goto-contract` — `53684f0bd8`
32. `nightly/android-phone-32-back-repeat-lifecycle` — `5f1685e379`
33. `nightly/android-phone-33-background-deep-link` — `af14d93556`
34. `nightly/android-phone-34-qml-qrc-escaping` — `fbac2f1cb9`
35. `nightly/android-phone-35-content-cache-stamp` — `f8de1537c0`
36. `nightly/android-phone-36-menu-deferred-action` — `58f1a6f39f`
37. `nightly/android-phone-37-people-request-validation` — `eb3d1c4f3e`
38. `nightly/android-phone-38-avatar-scale-contract` — `d7b2b532a9`
39. `nightly/android-phone-39-address-input-contract` — `611f6e4a01`
40. `nightly/android-phone-40-login-credential-lifetime` — `31f75abddb`
41. `nightly/android-phone-41-avatar-community-boundary` — `a2de0e061d`
42. `nightly/android-phone-42-avatar-url-contract` — `e3fa05e20e`
43. `nightly/android-phone-43-places-portal-ownership` — `f9ee2df7cc`
44. `nightly/android-phone-44-people-response-validation` — `45c0465751`
45. `nightly/android-phone-45-people-payload-validation` — `f53699435b`
46. `nightly/android-phone-46-apk-core-runtimes` — `4b64a30fa6`
47. `nightly/android-phone-47-apk-archive-uniqueness` — `180bcdfe5a`
48. `nightly/android-phone-48-apk-cache-contract` — `613b3a04c1`
49. `nightly/android-phone-49-apk-default-scripts` — `aeb5705083`
50. `nightly/android-phone-50-default-script-sync` — `f3377093ea`
51. `nightly/android-phone-51-device-apk-provenance` — `2a8bee67db`
52. `nightly/android-phone-52-device-permission-automation` — `d3fd9f56be`
53. `nightly/android-phone-53-release-bundle-gate` — `7430e6c299`
54. `nightly/android-phone-54-device-smoke-integrity` — `710b9eba06`
55. `nightly/android-phone-55-device-lifecycle-stress` — `f649a45656`
56. `nightly/android-phone-56-private-device-reports` — `27589e6ba9`
57. `nightly/android-phone-57-device-smoke-mock` — `a3d8ee3ec8`
58. `nightly/android-phone-58-atomic-device-summary` — `bff542c71a`
59. `nightly/android-phone-59-release-metadata-gate` — `7f0247b54a`
60. `nightly/android-phone-60-scope-audit` — `05b977ffa6`
61. `nightly/android-phone-61-device-smoke-failures` — `9ef52a86d5`
62. `nightly/android-phone-62-gradle-release-contract` — `e87215f1ba`
63. `nightly/android-phone-63-doctor-dependency-status` — `6ec106bbb0`
64. `nightly/android-phone-64-doctor-content-verification` — `a47915a3ba`
65. `nightly/android-phone-65-private-doctor-status` — `31b42564da`
66. `nightly/android-phone-66-private-device-output` — `6d74915440`
67. `nightly/android-phone-67-logcat-delta` — `1eba03cf62`
68. `nightly/android-phone-68-device-diagnostic-failures` — `501ba562d7`
69. `nightly/android-phone-69-exit-info-contract` — `79001db716`
70. `nightly/android-phone-70-page-size-markers` — `a7b623f89a`
71. `nightly/android-phone-71-device-target-contract` — `a8980c358c`
72. `nightly/android-phone-72-device-runtime-contract` — `9db8bc8ac8`
73. `nightly/android-phone-73-apk-identity-preflight` — `4c56cd603a`
74. `nightly/android-phone-74-apk-sdk-preflight` — `07de073444`
75. `nightly/android-phone-75-apk-permission-preflight` — `cd9763aa09`
76. `nightly/android-phone-76-apk-debug-contract` — `1536cb9055`
77. `nightly/android-phone-77-apk-package-preflight` — `518a3d5737`
78. `nightly/android-phone-78-local-preflight-order` — `56c92b1418`
79. `nightly/android-phone-79-private-adb-errors` — `27002f7922`
80. `nightly/android-phone-80-adb-phase-errors` — `df9474836b`
81. `nightly/android-phone-81-installed-apk-read-failure` — `7ee070ac89`
82. `nightly/android-phone-82-device-summary-status` — `37733e4916`
83. `nightly/android-phone-83-device-smoke-cleanup` — `82286fdd80`
84. `nightly/android-phone-84-cleanup-failure-contract` — `391805b8c2`
85. `nightly/android-phone-85-exit-info-phase-errors` — `3038e4adc8`
86. `nightly/android-phone-86-preflight-override-guard` — `6bf12937cd`
87. `nightly/android-phone-87-apk-metadata-gate` — `b89b1c7f4b`
88. `nightly/android-phone-88-variant-debuggable-gate` — `bcef8b1c81`
89. `nightly/android-phone-89-apk-version-metadata` — `ecfec1c1b3`
90. `nightly/android-phone-90-apkanalyzer-errors` — `488fb4bf47`
91. `nightly/android-phone-91-nightly-handoff` — `a2672c4ae7`
92. `nightly/android-phone-92-cache-digest-gate` — `4d6c434d63`
93. `nightly/android-phone-93-cache-manifest-limits` — `305ce9f3b4`
94. `nightly/android-phone-94-native-library-allowlist` — `4cf23fc7a6`
95. `nightly/android-phone-95-package-entry-integrity` — `1134b9092b`
96. `nightly/android-phone-96-package-layout-boundary` — `46a1cf115c`
97. `nightly/android-phone-97-private-elf-errors` — `c44a29b7dc`
98. `nightly/android-phone-98-private-package-errors` — `1d7f13300d`
99. `nightly/android-phone-99-central-directory-padding` — `13db75b136`
100. `nightly/android-phone-100-trailing-zip-data` — `bf5ca533b6`
101. `nightly/android-phone-101-complete-zip-integrity` — `133f4c3873`
102. `nightly/android-phone-102-zip-symlink-rejection` — `891449215f`
103. `nightly/android-phone-103-safe-archive-paths` — `bbc18b3420`
104. `nightly/android-phone-104-canonical-archive-paths` — `036af84614`
105. `nightly/android-phone-105-package-resource-limits` — `0e93b71623`
106. `nightly/android-phone-106-cache-asset-coverage` — `95a6c850c8`
107. `nightly/android-phone-107-qml-module-boundary` — `a37b4e3ac7`
108. `nightly/android-phone-108-private-preflight-paths` — `4fa4eace60`
109. `nightly/android-phone-109-private-apk-hash-errors` — `a44dc0efb1`
110. `nightly/android-phone-110-private-summary-write-errors` — `e39b0c7897`
111. `nightly/android-phone-111-report-setup-failures` — `2f38c788ca`
112. `nightly/android-phone-112-late-summary-failure` — `b12135379e`
113. `nightly/android-phone-113-private-benchmark-adb` — `3012eeec08`
114. `nightly/android-phone-114-benchmark-report-preflight` — `6d95343897`
115. `nightly/android-phone-115-private-benchmark-setup` — `48d8101544`
116. `nightly/android-phone-116-private-benchmark-publish` — `45408ac063`
117. `nightly/android-phone-117-benchmark-cleanup` — `f579bcfb7e`
118. `nightly/android-phone-118-benchmark-device-contract` — `ffcc39e6fa`
119. `nightly/android-phone-119-benchmark-phase-errors` — `7fa608d3ab`
120. `nightly/android-phone-120-bounded-benchmark-runtime` — `6ad488c062`
121. `nightly/android-phone-121-benchmark-signal-test` — `30af183d87`
122. `nightly/android-phone-122-benchmark-interrupt-test` — `e9a7736cc3`
123. `nightly/android-phone-123-benchmark-framestats-error` — `14ac38f578`
124. `nightly/android-phone-124-partial-summary-cleanup` — `f1f68c096f`
125. `nightly/android-phone-125-discoverable-temp-report` — `34b3e36628`
126. `nightly/android-phone-126-failed-temp-report-cleanup` — `8af0cc8bd1`
127. `nightly/android-phone-127-report-mode-cleanup` — `bfa652240e`
128. `nightly/android-phone-128-raw-mode-cleanup` — `2e2c58a547`
129. `nightly/android-phone-129-device-contract-fixtures` — `961b5537ec`
130. `nightly/android-phone-130-pico-benchmark-rejection` — `779f197b29`
131. `nightly/android-phone-131-three-hour-handoff` — `e69448dbd6`
132. `nightly/android-phone-132-private-raw-cleanup-error` — `974767aa7b`
133. `nightly/android-phone-133-required-benchmark-cleanup` — `489a1c238e`
134. `nightly/android-phone-134-device-preflight-handoff` — `01310b6cfe`
135. `nightly/android-phone-135-benchmark-documentation` — `9675ab2a75`
136. `nightly/android-phone-136-systemd-service-guard` — `37d5435496`
137. `nightly/android-phone-137-prebuilt-16k-delta` — this task's commit

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

1. Build a current debug and signed release APK from the final commit. Require
   the combined metadata/content/ELF/zipalign/padding gate, record SHA-256, run
   `PHONE_EXPECT_DEBUGGABLE=1` and `0` smokes respectively, and accept only
   summaries ending in `cleanup_force_stopped=1` and `test_status=passed`.
2. On one Adreno and one Mali phone, perform clean install/cold launch on an
   API 26–29 device and an API 30+ device; cover microphone accept and deny,
   native-library loading, TLS, and a neutral `overte:` deep link.
3. Exercise login success, invalid credentials, cancellation, gesture/physical
   Back, IME resize, background/foreground, and focus release against both a
   metaverse account and a domain login.
4. Verify landscape orientations on flat, notched, hole-punch, waterfall, and
   rounded displays: tablet edges, close button, portrait-sized transition,
   DPI scaling, system-bar reveal, keyboard, and all retained Settings fields.
5. Connect to live domains and repeat tablet open/app/Home/close cycles for
   Audio, Menu, Shield, People, Avatar, Places, Home, Tutorial, and Emote;
   confirm no world-control touch-through and no stale signal/timer state.
6. Stress Emote play/stop/switch, movement interruption, cache-cold animation
   loading, and background/foreground; the avatar must always regain normal
   locomotion.
7. Validate Audio input/output devices, mute, push-to-talk, sliders, People
   levels/actions, Places slow/offline/federated responses, Avatar bookmarks
   and wearables, and reconnect after network loss or process backgrounding.
8. Run the 16-KiB APK/ELF gate on the produced release artifact, inspect only
   PID-filtered aggregate diagnostics, and sustain the graphics benchmark long
   enough to assess frame pacing, memory, temperature, and battery without
   retaining identifiers or raw logs.
