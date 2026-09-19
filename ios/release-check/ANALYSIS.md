# Repository analysis and scope decisions

Analysis baseline: `apple-ios`, revision `f7cd7472b6`. This document records source
inspection, not a build, scanner result, security certification or release approval.

## Product selection

The fork separates `main`, `apple-main`, `apple-ios`, Android phone and Pico
product branches. `main` alone does not contain the complete iOS product.
The gate belongs to `apple-ios`. No Android/Pico job, shared runtime source,
upstream dependency implementation or existing workflow is modified.

Two distinct iOS products are present:

- Root `CMakeLists.txt` routes `OVERTE_IOS_BOOTSTRAP_ONLY=ON` to
  `ios/CMakeLists.txt`, producing `OverteIOSBootstrap`. This UIKit/Metal probe
  does not establish acceptance of the full client.
- The integrated path configures the root graph, `interface/CMakeLists.txt`,
  shared libraries and `ios/integration/CMakeLists.txt`, producing `Overte`.
  This gate selects that target, Release, iphoneos and arm64.
- `OVERTE_IOS_E2E_TEST_BUILD` selects separate metadata and native accessibility
  hooks. It is a test product and must not be distributed as the release product.
  Device evidence must identify its E2E IPA and a reviewed production/E2E pair.

The platform overview still describes an experimental port. Existing documents,
build recipes and checkpoints are evidence of implementation intent, not proof
that all current branches/checkpoints have completed physical acceptance.

## Actual build inputs identified by reading the build files

`ios/build-ios.sh configure --client-graph` uses the Qt iOS CMake frontend,
the staged Conan toolchain and Xcode generator. `build` without that path selects
the bootstrap. The new cold-build driver therefore reuses `configure
--client-graph` and explicitly builds `--target Overte`.

`interface/CMakeLists.txt` links shared, workload, task, octree, ktx, gpu,
procedural, graphics, graphics-scripting, render, pointers, recording, hfm,
model-serializers, networking, material-networking, model-networking,
model-baker, entities, avatars, audio, audio-client, animation, physics,
render-utils, entities-renderer, avatars-renderer, ui, qml, midi, controllers,
plugins, image, platform, ui-plugins, display-plugins, input-plugins and shaders.
Further dependencies and conditional backend targets enter transitively.
`script-engine` is relevant through includes/consumers and static non-JIT V8.
The iOS Vulkan path includes `gpu-vk` and `vk` and still has explicitly documented
GLES/Qt compatibility surfaces; desktop GL assumptions cannot simply be applied.

`ios/integration/CMakeLists.txt` adds entity/rendering gates, native Keychain
account storage, redacted diagnostics, AVAudioSession audio, contained WebKit,
world observation, memory pressure handling and native metrics. Interface also
adds `ios/ui/IOSTouchUiMetrics.mm`. Apple frameworks include UIKit, Metal,
MetalKit, Foundation, AVFoundation, Security, LocalAuthentication and WebKit;
the bootstrap additionally exposes native platform probes. Framework/API use
must be checked in the chosen target, not inferred from a framework name alone.

Resources are particularly important:

- `generate_qrc` covers `interface/resources` with `GLOBS *`. Android phone
  exclusions do not automatically apply to iOS.
- The iOS post-build path copies the entire `scripts` tree, fonts and serverless
  tutorial/redirect data, and embeds `resources.rcc`.
- iOS adds `ios/resources/Assets.xcassets` and `PrivacyInfo.xcprivacy`.
- The release Info.plist template is `InterfaceInfo.plist.in`, not the bootstrap
  `Info.plist.in` and not `InterfaceE2EInfo.plist.in`.

Consequently the conservative source inventory includes all shared libraries,
Interface resources, scripts, relevant native codecs, build macros, iOS tools
and shared test infrastructure. It excludes Android/Pico-only trees and jobs.
Shared files may still contain inactive platform branches; findings from this
inventory are candidates, not proof of linked reachability. After a clean build,
CMake File API `codemodel-v2` walks `Overte` and its target dependency closure in
the Release configuration, records sources, generated/external sources and link
fragments. Bundled resource roots remain in scope even if not compilation units.

## Dependencies and toolchain

`ios/versions.env` currently defines iOS 17, Xcode/SDK 26, Qt 6.11.1,
CMake >=3.24, Conan 2.25.2 and Python >=3.11. Host profiles use macOS arm64;
the device Conan profile is `ios/conan/profiles/ios-arm64`.

`ios/conanfile.py` is separate from the desktop recipe. It includes Bullet,
cgltf, Draco, image/texture packages, GL dispatch, GLM/GLI, JSON libraries,
static oneTBB, OpenEXR, OpenSSL, VHACD, zlib, Opus and WebRTC audio processing.
Shader tools are host dependencies. `ios/dependencies.json` records required,
disabled/deferred and shipping classes; it is not a resolved transitive lockfile.
Qt, V8 and MoltenVK require separate audited inputs. The existing generated
Conan SBOM does not itself prove completeness for these SDKs or media.
Unversioned package recipe revisions and missing vulnerability identifiers must
not be mistaken for pinned, fully scanned dependencies.

The existing CI restores large Qt/V8/compiler checkpoints. A pre-release cold
build must explicitly inventory its immutable SDK inputs and use a fresh source
checkout, fresh Conan home and empty application build directory. The new driver
does not inherit compiler-cache or signing environment variables. It still uses
installed Xcode/Python/host tools; it is not a hermetic OS image or a guarantee of
bit-identical signed IPAs. Network dependency resolution uses a reviewed Conan
lockfile. Cached SDK ZIPs must have audited source provenance and SHA-256 values.

## Existing checks reused

- `ios/tools/audit-conan-graph.py` and `generate-sbom.py`.
- `verify-client-bundle-info.py`, `verify-e2e-test-build.py`,
  `verify-privacy-manifest.py`, `verify-ios-static-runtime.py`,
  `verify-dsym-content.py`.
- `ios/tests/run-tests.sh` for existing host contracts in the clean-build group.
- Shared `tests/device/catalog.json`, `run.py`, the Appium iOS adapter,
  `ios-flat-touch-policy.json` and `verify-result.py`.
- Existing domain, asset, sound, movement, look, jump, tablet, upgrade,
  permission, recovery, lifecycle and stability modules are reused unchanged.

The native `ios/device-tests` adapter currently advertises only bounded
launch/terminate; it cannot establish the broad functionality requested here.
The Appium/shared catalog path is the appropriate integration surface, but
capability absence remains a failure with `--require-complete`. A verified
result requires an exact source/artifact identity, physical-device class,
complete expected module set and no skipped/failed modules.

The shared idle soak can pass using process/foreground observations without
resource telemetry. The new gate therefore separately requires resource
measurements; it never equates that process-only pass with memory/leak/CPU proof.
The existing network-fault case stops the fixture domain stack; real radio loss,
slow/unstable links and some iOS permission changes need independent evidence.

## Distribution boundary

Repository documentation describes unsigned developer IPA handoff, local
developer signing and separately authorized Sideloadly installation. App Store
submission is outside the currently documented milestone. The default profile is
therefore `sideload-unsigned`, with separate `development-signed`, `ad-hoc` and
`app-store` inspection policies. No profile performs signing or upload.

The source entitlements are currently empty. Microphone and local-network usage
descriptions exist; ATS allows local networking. The manifest declares file
timestamps, boot time, disk space and user defaults, no collected data and no
tracking. These existing declarations are input to review, not new conclusions
about network behavior or legal compliance.

## Original implementation-session validation boundary

The original implementation allowed only file reading, source-level reasoning
and parsing the new Python/JSON/TOML/YAML documents. A subsequent user instruction
authorized local regression tests, pinned tool setup, and static qualification.
See QUALIFICATION.md. CMake/Xcode builds, Conan resolution, device operations and
workflow dispatch have still not been performed.
