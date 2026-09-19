# Inspected Android Phone build closure

Analysis baseline: `origin/android-phone` commit
`b170f30f3a` (local remote-tracking snapshot inspected on 2026-09-19).
The canonical `main` checkout has no complete Android tree. This gate therefore
lives entirely below `android/phone/quality-gate/` on a Phone topic branch.

## Build graph and packaged inputs

| Entry | Android contribution |
|---|---|
| `android/phone/settings.gradle` | Single `:phoneInterface` application; Google/Maven Central repositories. No Pico Gradle project is selected. |
| `android/phone/build.gradle` | AGP 8.13.2, explicit release version validation. |
| `android/phone/apps/phoneInterface/build.gradle` | `org.overte.phone`, min 26, target/compile 36, NDK 27.3.13750724, CMake 3.31.6, Java 17, ARM64 (separate x86 emulator mode). |
| Phone Java/C++/resources and manifest | Permissions/lifecycle/touch/deep links and native `phoneInterface` library. |
| `android/common/libraries/qt/src/main/java` | Shared Qt Android Java runtime sources, compiled into Phone. |
| `security/redaction/java` | Root-level shared sanitizer included through `../../../../security/redaction/java` from the application module. |
| `android/common/src` | Qt input connection compatibility and Android offscreen GL implementation injected into native targets. |
| `android/common/cmake/overte-android-*` | Toolchain/bootstrap, Qt/WebEngine compatibility, source-built host tool handoff. |
| Root CMake → Phone CMake → `interface/CMakeLists.txt` | Builds shared Interface and recursively linked Overte libraries, not only Android Java. |
| `libraries/` | Shared/networking/audio/script engine/render/physics/entities/avatar/UI/controllers/plugins/shaders and their transitive dependencies. Actual translation units are captured after configuration. |
| `cmake/`, root `conanfile.py`, `provenance/` | Build macros, configuration and dependency/provenance inputs; conservative audit includes them even when overridden by the Phone graph. |
| `interface/compiledResources`, `interface/resources`, QRC inputs | RCC, QML, icons/fonts/textures/models/avatars, serverless resources. Serverless JSON is separately copied; referenced resources live in RCC. |
| `scripts/` | Copied runtime scripts/media. Existing Phone exclusions remove maps, web-types, simplifiedUI, developer, tutorials, communityScripts and specific unused desktop/voxel assets. |
| Source-built Qt package | Trimmed native plugins/libraries, Qt Android JARs, QML modules and generated `android_rcc_bundle.rcc`. QtTest/QuickTest remain linked; their names alone are not debug-payload proof. |
| Gradle runtime | Guava 23.0 plus transitive runtime dependencies and local source-built Qt JARs. JUnit/Robolectric/AndroidX instrumentation libraries belong to test configurations. |
| `android/phone/fdroid/conan/target.conanfile.py` | Imports `android/common/conan/conanfile-pico.py` despite its historical name; Qt 5.15.18-2026.01.04 source override, separate host tools. |
| F-Droid manifests/recipes/profiles/locks | Public source closure, recipe exports, bootstrap/host/target locks, Qt source/license locks, toolchain acquisition constraints. |

Root CMake selects `HIFI_ANDROID_APP=phoneInterface`. Phone CMake links
`shared task networking qml image model-serializers hfm render-utils physics
entities octree gl gpu` and Interface. Interface extends this to workload,
material/model networking/baking, avatars, audio/audio-client, animation,
render/entities-renderer/avatars-renderer, UI, auto-updater, MIDI, controllers,
plugins, platform, input/display/UI plugins and shaders. `PLATFORM_GL_BACKEND`
and `PLATFORM_PLUGIN_LIBRARIES` are conditional, so the prebuild scan must not
claim an exact configured closure. Native compile commands and package evidence
are authoritative refinements.

The gate scans both `android/common/` and all shared candidate source/resource
roots. Legacy Phone/framePlayer/Quest/Pico product source and iOS source are not
selected for product scans. Existing shared directories contain tests and
alternative compatibility files, so heuristic findings are explicitly reviewable.
The complete build archive still retains the repository's ordinary source tree;
no source pruning changes the build's semantics.

## Existing infrastructure reused

- `fdroid/scripts/build-dependencies.sh`: fresh offline source preparation and
  bootstrap/host/target Conan builds, closed remotes, exact profiles, source store,
  sentinel, Qt composition and host-tool staging.
- `fdroid/scripts/cold-build.sh`: architectural reference for Podman isolation;
  not invoked because its proof version and local image tag are unsuitable for
  a general release gate. Existing `build-release.sh build` is deferred.
- `fdroid/container/Containerfile`: digest-bound F-Droid base with exact selected
  build clients; some apt/pip transitive acquisition remains a provenance review.
- `tests/check-phone-apk-16k.sh` and `check-phone-apk-contents.py`: metadata,
  native allowlist, cache manifest/digests, ELF/ZIP alignment and AAB checks.
- Phone release signing is optional, has no repository defaults; this runner
  passes no signing inputs. The unsigned artifact is the F-Droid build result.
- `tests/device/run.py`: target locks, cleanup, timeouts, capability checks,
  private selectors, JUnit, source/artifact/installed-candidate identity.
- Bound `tests/device/adapters/android-phone/` wrappers: real physical Phone
  ADB/Appium path, independent SH-009 candidate inputs; no mock acceptance.
- `tools/release/`: complete license/source/SBOM/provenance contract, used as a
  reconciliation reference; no release bundle publishing action is invoked.
- Existing `.github/workflows/android-phone-*` and shared device Jenkins flow:
  inspected as infrastructure context; unchanged. This gate can be invoked from
  any local worker through the same command, without a proprietary CI service.

## Known qualification gaps

No gate execution was performed. No current release-readiness result exists.
Static inspection identified Guava's old declaration, potentially large shared
source/resource scope, a deferred high-level F-Droid adapter, proof-only values
in the previous cold-build script, and debug-only E2E instrumentation. These are
inputs to future checks, not newly measured vulnerabilities or device failures.
Public availability, all asset licenses, binary origin and supported device
observations must be established by the future run and the required reviews.
