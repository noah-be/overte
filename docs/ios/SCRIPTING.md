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

Until an audited package exists, the integrated client configuration stops with
an actionable CMake error. A developer supplies the package explicitly:

```bash
export OVERTE_IOS_V8_ROOT=/absolute/path/to/overte-v8-ios
```

Expected layout:

```text
include/node/v8.h
lib/libnode.a
```

`libv8_monolith.a` may be supplied instead of `libnode.a` after the ABI and
initialization paths pass the existing script-engine tests.

## Acceptance gate

The package is accepted only after:

- architecture and symbol inspection confirms a static arm64 archive;
- the process has no JIT or executable-memory entitlement;
- system scripts start and stop repeatedly without leaked isolates;
- downloaded JavaScript remains interpreted data;
- native Node modules and process-spawning APIs are unavailable; and
- the complete script compatibility suite passes on a physical device.

