<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS dependency policy

Every native dependency must be classified before it enters an iOS app bundle.

| Class | Meaning | Initial examples |
| --- | --- | --- |
| required | Needed by the first usable client | Qt Core/Gui/Qml/Quick, Bullet, Opus, WebRTC audio processing, OpenSSL, zlib |
| graphics-spike | Included only by the selected backend | MoltenVK, Vulkan headers, SPIR-V tools, glslang |
| replace | Desktop implementation is not usable on iOS | Qt WebEngine to WKWebView/Qt WebView |
| non-JIT | Must run without executable-memory assumptions | libnode/V8 |
| disabled | Not part of the first iOS client | Steamworks, Discord RPC, OpenVR, OpenXR, Oculus, SDL device plug-in, Sixense, Neuron |
| host-only | Build-time tool, never shipped in the app | Scribe and shader/resource generators |

## Required properties

An iOS dependency must:

- build for `arm64` device and `arm64` simulator with the selected deployment
  target;
- be linked statically unless it is an Apple system framework;
- expose no unsigned runtime plug-in requirement;
- avoid JIT or writable-and-executable memory;
- provide license metadata for the application bundle;
- produce deterministic package metadata; and
- pass architecture and forbidden-library checks before packaging.

The build must fail, rather than silently enable a disabled desktop dependency.

## Conan build context

Cross compilation uses the checked-in `ios-arm64` or
`ios-simulator-arm64` profile for target libraries and the separate
`macos-arm64` profile for native tools that execute on the pinned macOS 26
runner. The dependency command names both profiles explicitly. It must not
depend on Conan's mutable, user-global `default` profile, which is absent in a
fresh CI environment and could otherwise silently change the build-tool ABI.

## Entity pipeline direct-requirement audit

`ios/tools/audit-entity-conan-contract.py` scans the CMake dependency macros
and external header families used directly by `networking`, `octree`,
`entities`, and `entities-renderer`. Every discovered Conan package must be an
enabled, shipping entry in `dependencies.json` and an explicit requirement of
the staged iOS recipe. This complements the resolved-graph audit: it catches a
missing recipe edge before Conan can produce an apparently valid but incomplete
graph.

The current direct set is OpenSSL, oneTBB, GLM, and Bullet. Qt modules are
provided by the separately validated Qt iOS cache, while internal Overte target
edges remain CMake targets and are not duplicated as Conan packages. The audit
uses an explicit header/macro mapping so a newly introduced external family
must be reviewed and added deliberately rather than guessed from transitive
includes.

QuaZIP is intentionally absent from the staged Conan graph. The repository's
legacy `quazip/1.4` recipe requires Qt 5 and expands into desktop OpenGL and
database dependencies. The integrated Qt 6 target must use QuaZIP 1.7 or newer,
built against the exact same audited Qt 6 iOS package; it may not resolve its
own Qt major independently. The staged TLS graph uses OpenSSL 3.5.7 so the iOS
port does not establish a new dependency on the legacy 1.1 ABI.
