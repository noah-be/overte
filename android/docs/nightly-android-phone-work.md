# Android phone nightly work

This file records the cumulative, device-free Android phone work based on
`origin/feature/android-phone-support`. Real-device and emulator tests are out
of scope for this worktree and are called out explicitly where still needed.

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
