# Apple Universal Touch UI validation — 2026-08-22

## Scope and source

- Validation branch: `test/universal-touch-ui-apple-validation`
- Required base: `origin/main` at `da5309b3d179a56e25960966a0b1367e2d655649`
- Apple baseline: `origin/apple-ios` at `2f1653f393b0b6f2a2b513645d12259253780c14`
- Validation revision: `e6bdf07b4135f386014fef691b4e41d184771c80`
- Baseline merge: `7d3550bc0b` (`test(apple): establish iOS validation baseline`)

The repository workflow assigns platform-neutral touch layout and capability
defaults to `main`, Apple-family integration to `apple-main`, and the iPhone/iPad
adapter, packaging, runtime integration, and policy to `apple-ios`. The validation
branch therefore starts at `origin/main` and merges the current `origin/apple-ios`
baseline. It contains no Android product-branch merge.

## Automated results

| Gate | Result | Evidence |
| --- | --- | --- |
| Shared native host tests | PASS | 20/20 CTest cases |
| Shared JavaScript tests | PASS | 50/50 Node tests plus 20 lifecycle cycles |
| Shared QML tests | PASS | 52/52 Qt Quick tests |
| Shared JVM/Robolectric tests | PASS | Gradle 8.13 with cached JDK 21 |
| iOS Linux host contracts | PASS | Complete `ios/tests/run-tests.sh` |
| iOS syntax/metadata contracts | PASS | Python compile, Bash parse, Conan inspect |
| GitHub macOS host contracts | PASS | Run `32569811097`, job `97023575183` |
| Apple device-SDK compile/package | PASS | unsigned arm64 device IPA, job `97023788418` |
| Apple simulator build/package | PASS | unsigned arm64 simulator app, job `97023788367` |
| One iPhone simulator smoke | PASS | install, launch, deep link, terminate, shutdown |

The simulator artifact is the native bootstrap. It verifies Apple bundle,
lifecycle, safe-area/orientation probe plumbing, basic touch input, deep-link,
and packaging boundaries. It does **not** prove rendering or interaction of the
experimental integrated Qt/Overte client or every Universal Touch UI screen.

## Findings and classification

1. **Apple-specific CI policy:** manual bootstrap dispatches previously selected
   both iPhone and iPad. Per validation policy, manual dispatch now defaults to
   exactly one iPhone while push and touch-relevant pull-request coverage retain
   both families. Fixed in `e6bdf07b41`; the contract test was updated with the
   workflow. This change belongs to `apple-ios` when promoted.
2. **Environment-only:** the system JDK 25 is intentionally rejected by the
   reproducible Robolectric gate. Re-running with the existing persistent JDK 21
   cache passed. This is not a product defect.
3. No shared Universal Touch UI defect was reproduced by the executable host,
   JavaScript, or QML suite.
4. No Apple runtime defect was reproduced by the bootstrap simulator and
   device-SDK gates. Full-client and physical-device coverage remains open, so
   this is not a claim that no such defects exist.
5. **Apple-specific privacy contract:** the physical-device result schema
   required publication of a device model even though acceptance needs only the
   form factor and OS version. Commit `f2cac492ca` removes that field and rejects
   private device metadata in result records.
6. **Apple-specific Fedora handoff readiness:** commit `b5ce2ec916` adds a strict
   Full Client Sideloadly verifier, privacy-filtered Fedora syslog capture, and a
   22-case iPad result generator. Their mock contracts and the complete iOS host
   suite pass without hardware.

## Toolchain, parallelism, and caches

- Local host: Fedora Linux, 16 logical CPUs, 31 GiB RAM.
- Local: GCC 16.1.1, CMake 4.3.0, Python 3.14.6, Node 24.18.1,
  Conan 2.25.2, Qt/QML test runner 5.15.18 (project Qt installation 6.11.1).
- JVM: Temurin 21.0.12 from
  `/home/user/.cache/codex-overte-touch-ui-tests-20260814/jdk21`; restore path
  verified by a complete successful host rerun.
- Apple: GitHub `macos-26`, Xcode 26.6 build 17F113, iOS/iPhoneSimulator SDK
  26.5, deployment target 17.0, arm64, Debug.
- Xcode invoked `-parallelizeTargets -jobs 3`, matching the workflow's bounded
  memory policy. Local native tests used their CMake parallel build default on
  the 16-core host.
- Existing local caches inspected: ccache (`/home/user/.cache/ccache`, 293 MiB),
  Conan (`/home/user/.conan2`), and the persistent JDK 21 cache. The second native
  host build reused its generated CMake tree. No reusable local Xcode/Simulator
  cache exists because the host is Linux. The expensive integrated Qt build was
  not run after the requested reduction to one iPhone bootstrap smoke; its
  checked-in GitHub workflow retains content-addressed Qt checkpoint/cache
  restoration for a future run.
- Fedora already provides the `libimobiledevice` libraries and `usbmuxd`.
  `libimobiledevice-utils` is still required for `idevice_id` and
  `idevicesyslog`; automatic installation stopped safely because `sudo` needs an
  interactive local password.

## Artifact checksums (SHA-256)

- `0442-OverteIOSBootstrap-Debug-simulator.zip`:
  `1e1451e7c678d362f11f3cc9dc953c7bbb663d7f001732517ab1db2380cf198e`
- `0442-OverteIOSBootstrap-Debug-device-unsigned.ipa`:
  `a8740b0b33ad3d55a284135575bfe26d6bbfe32a5474961cd0a5173f21e38a59`
- Shared host JUnit (`TEST-android-host.xml`):
  `1c244ff40fa5be3cacf93f54aa6d81e3a1033d218798123ff0d4192dc93ffafd`
- Shared JavaScript JUnit: `664da5b223b2730e8689c217c8848e875972a2c6e6a3b32f96d8b756f5b4474c`
- Shared QML JUnit: `154136e814a38cc704c8f19098f1bd089486ed9985208e71f27a376d5b342afa`
- Shared native JUnit: `9e8a5e630d589f09a3a324c0f071fbefe50a00589f382934df35236e1f81b8a0`

Downloaded artifacts and JUnit files are retained locally under
`validation-artifacts/`; no device identifier or user information is recorded
in this protocol.

## Physical iPad manual touch journey

Use a Sideloadly-signed integrated Full Client built from the recorded revision.
Verify the unsigned handoff with `ios/tools/verify-sideload-handoff.py`, record a
new checksum for the signed derivative, and capture only filtered Fedora logs
with `ios/tools/fedora-ipad-log.py`. Do not record device identifiers, model, or
personal information.

1. Cold-launch in portrait and confirm every edge respects the safe area; open
   and close the tablet using touch only.
2. Traverse Home, Places, People, Avatar, Audio, Security, Settings, and General
   Preferences. Verify Back/Close on every nested screen and confirm no Android
   system-back assumption is visible.
3. Rotate to landscape on each major screen. Confirm live reflow, stable
   selection, readable text, minimum 48-pixel touch targets, and no clipped or
   unreachable actions.
4. Exercise full-screen, Split View, and Stage Manager resizing where available.
   Confirm compact/medium/expanded transitions and asymmetric safe-area handling.
5. In login, address, search, and allowlist fields, show/hide the software
   keyboard, move focus forward/back, rotate while focused, and confirm the
   focused control remains visible and teardown dismisses the keyboard.
6. Increase Dynamic Type through normal, approximately 1.3, 1.5, and above the
   supported cap. Confirm bounded scaling, reflow, and no control overlap.
7. Navigate by direct touch, then attach a hardware keyboard/pointer if
   available. Verify focus order, hover/pointer behavior, and return to touch.
8. Send the app to background from an open tablet and from an edited text field;
   resume after short and long intervals. Confirm preserved navigation, valid
   rendering, audio/input recovery, and no duplicate action handling.
9. Open a valid `overte://` link from outside the app during cold start and warm
   resume. Verify one navigation, then close/back to the prior surface.
10. Repeat rapid open/close, rotation, keyboard, and background/foreground cycles
    ten times. Record crashes, hangs, lost focus, stale insets, and visual jumps.

## Tests not yet executable and prerequisites

- Integrated Qt/Overte full-client simulator Touch UI: requires opting into the
  expensive integrated GitHub workflow and its validated Qt checkpoints; this
  was intentionally not run after the scope was reduced to one iPhone bootstrap.
- Physical iPad automated smoke/lifecycle: the macOS executor is unavailable;
  Fedora can capture and validate logs after a complete Full Client IPA has been
  signed and installed manually through Sideloadly.
- Physical iPad manual journey: requires that IPA, a trusted/unlocked iPad, and a human
  observer; Split View/Stage Manager, external-input, Dynamic Type, VoiceOver,
  camera/microphone, thermal, and background-suspension observations are
  device-only.
- Complete iPadOS acceptance remains pending even though the unsigned device SDK
  build passed. No serial number, UDID, model, or user identity may enter logs or
  committed evidence.
- Fedora live-capture doctor: requires local installation of
  `libimobiledevice-utils`; all command, redaction, timeout, privacy, and artifact
  behavior is already covered by hardware-free mocks.
