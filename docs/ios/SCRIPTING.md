<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# JavaScript runtime on iOS

Overte depends on JavaScript for system behavior and world content, so simply
removing the script engine is not an acceptable first-client solution.

The iOS runtime package must be a static arm64 build that does not require JIT,
writable executable memory, WebAssembly code generation, dynamic native
modules, or a separately launched helper process. The application also sets
V8's `--jitless` and `--no-expose-wasm` runtime flags as a fail-closed layer.

CI builds V8 12.4.254.21 from its official source tag using a pinned
`depot_tools` revision. The package is an independent, deterministic cache
checkpoint: a failed application build reuses the validated archive instead of
rebuilding V8. Developers may build and select the same package explicitly:

```bash
ios/tools/build-v8-ios.sh build
export OVERTE_IOS_V8_ROOT="$PWD/build-ios/external/v8-ios"
```

Expected layout:

```text
include/node/v8.h
lib/libv8_monolith.a
```

The build records its complete GN arguments beside the package. It targets the
device `arm64` ABI, statically links `v8_monolith`, embeds startup data, and
disables JIT and WebAssembly generation. `ios/tools/build-v8-ios.sh validate`
checks those invariants and the Mach-O architecture before CMake runs.

V8 derives its internal `v8_jitless` setting for an iOS device build. The
recipe additionally enables V8 lite mode, which fail-closes the optimizing
compilers and is asserted by V8 to be incompatible with WebAssembly.

## Acceptance gate

The package is accepted only after:

- architecture and symbol inspection confirms a static arm64 archive;
- the process has no JIT or executable-memory entitlement;
- system scripts start and stop repeatedly without leaked isolates;
- downloaded JavaScript remains interpreted data;
- native Node modules and process-spawning APIs are unavailable; and
- the complete script compatibility suite passes on a physical device.
