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

QuaZIP is intentionally absent from the staged Conan graph. The repository's
legacy `quazip/1.4` recipe requires Qt 5 and expands into desktop OpenGL and
database dependencies. The integrated Qt 6 target must use QuaZIP 1.7 or newer,
built against the exact same audited Qt 6 iOS package; it may not resolve its
own Qt major independently. The staged TLS graph uses OpenSSL 3.5.7 so the iOS
port does not establish a new dependency on the legacy 1.1 ABI.
