# macOS port status

Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0

The macOS port starts from the shared Apple branch after the iOS work was
merged. It does not yet have macOS runtime acceptance evidence.

## Goal

Produce an Overte desktop application that starts on a supported macOS host,
loads a local serverless scene and an online domain, and renders their entities.

## Strategy

The first executable baseline uses the existing desktop Qt 5 and OpenGL 4.1
path. It targets x86_64 first because the historical Qt WebEngine dependency
graph has known Intel packages. Server, tools and installer targets stay out of
the bootstrap build. Native arm64 and Vulkan through MoltenVK are follow-ups.

The serverless and online entity paths are shared with the other Interface
clients and converge on `EntityTreeRenderer`; no macOS-only protocol fork is
planned.

## Current evidence

| Gate | Status | Evidence |
| --- | --- | --- |
| Reproducible client-only configure | In progress | `macos/build-macos.sh` |
| Compile `Overte.app` on current Xcode | Not run | macOS CI required |
| Launch and first rendered frame | Not run | macOS runtime required |
| Load and render packaged serverless scene | In progress | `macos/ci/serverless-smoke.sh` |
| Connect to and render an online domain | In progress | `macos/ci/online-smoke.sh` |
| Switch serverless to online and back | Not run | Runtime smoke required |
| Native Apple Silicon build | Not run | Dependency audit required |

Last attempted CI: `macOS bootstrap` run `31401049683` at commit
`bc3a435597`. The modern Xcode host, Conan 2 tooling, repaired Qt 5.15.2 aqt
package and 35 dependency positions completed. CMake configure has not run yet
because dependency position 36, `libnode/22.22.3@overte/stable`, failed while
compiling Node's bundled dependencies. The recipe downloads GitHub's tag
archive. Those headers are present, but the recipe passes `RelWithDebInfo` to
Node's generated makefiles even though they only define internal include sets
for `Debug` and `Release`. The resulting empty include set produces the
misleading missing-header errors. The Conan cache from this run was saved
successfully.

## Acceptance gates

1. `Overte.app` launches without a crash and presents a first frame.
2. Loading `interface/resources/serverless/tutorial.json` populates the live
   entity tree and hands at least one entity to the render scene.
3. Loading an online `overte://` location sends an entity query, receives
   entity data, and hands at least one online entity to the render scene.
4. Switching serverless to online and back clears stale entities and remains
   stable for at least 60 seconds.
5. A model and texture load over the network, camera input works, and the app
   exits cleanly.

## Known risks

- The old guide selected Xcode 11.2 and the macOS 10.12 SDK. Those versions are
  obsolete and are intentionally not reproduced.
- Apple exposes deprecated OpenGL only up to 4.1. It is the shortest bootstrap
  path; MoltenVK is the intended fallback if it cannot run reliably.
- Desktop requires Qt WebEngine. The published Qt 5 aqt recipe incorrectly
  selects a Windows archive on macOS; `macos/conan/qt-aqt` repairs its Intel
  package locally. Native arm64 still requires a different Qt strategy.
- MoltenVK lookup, Vulkan surfaces and linker rules are currently iOS-only.
- The current macOS dependency blocker is the build-type mapping in the
  `libnode/22.22.3@overte/stable` recipe. A macOS-local recipe maps Conan Debug
  to Node Debug and all other configurations to Node Release, and pins Node's
  official release archive. The next step is native CI validation, followed by
  resuming the cached dependency build.

After the complete macOS plan and final status report, compare the retained
`feature/macos-support` branch against `apple-main` and `apple-macos` one last
time. Remove it only after confirming that it remains fully contained.

## Build

Install Xcode, CMake, Conan 2, Python 3, Node.js and `aqtinstall` in a Python
virtual environment, then run:

```bash
macos/build-macos.sh doctor
macos/build-macos.sh all
```

Defaults are `RelWithDebInfo`, x86_64 and Conan's `aqt` Qt package. Override
them with `OVERTE_MACOS_BUILD_TYPE`, `OVERTE_MACOS_ARCH`,
`OVERTE_MACOS_QT_SOURCE`, `OVERTE_MACOS_BUILD_DIR`, and
`MACOSX_DEPLOYMENT_TARGET`.
