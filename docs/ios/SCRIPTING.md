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
`depot_tools` revision. The package uses a three-level recovery order: an exact
validated output cache, then a provenance-checked durable workflow artifact,
then per-translation-unit `sccache`; only a miss at all three levels performs a
full rebuild. The output identity is canonical JSON containing the V8 and
depot revisions, target architecture/environment, Xcode build, SDK version and
build, Apple Clang version and binary digest, deployment target, exact GN flags
and only the patches applicable to that platform. Run IDs, workspace paths,
timestamps, telemetry changes and simulator-only patches are not part of the
device identity. A failed application build therefore reuses the validated
archive instead of rebuilding V8. Developers may build and select the same
device package explicitly:

```bash
ios/tools/build-v8-ios.sh build
export OVERTE_IOS_V8_ROOT="$PWD/build-ios/external/v8-ios"
```

The simulator package is a separate Mach-O platform build even on an arm64
host. Select it explicitly; the validator records and rejects a mismatched
`target_environment`:

```bash
OVERTE_IOS_V8_PLATFORM=simulator \
OVERTE_IOS_V8_ROOT="$PWD/build-ios/external-simulator/v8-ios" \
  ios/tools/build-v8-ios.sh build
```

Expected layout:

```text
include/node/v8.h
lib/libv8_monolith.a
```

The build records its complete GN arguments and canonical identity beside the package. It targets the
selected device or simulator `arm64` ABI, statically links `v8_monolith`, embeds startup data, and
disables JIT and WebAssembly generation. `ios/tools/build-v8-ios.sh validate`
checks those invariants and the Mach-O architecture before CMake runs.
Validation recomputes the identity from the selected Xcode, SDK and compiler,
so an output from an incompatible toolchain cannot be accepted merely because
its directory layout looks valid.
Because the output is a static archive rather than an installable app, its GN
configuration disables code signing; signing remains owned by the final Overte
bundle packaging step.
The device archive uses Xcode's SDK libc++ (`use_custom_libcxx=false`), as
required by V8's iOS cross-build guidance; the historical Chromium libc++ in
this V8 tag is not mixed with the current Xcode SDK headers.

The builder deliberately skips V8's unrelated test-Python hook: V8 12.4 pins
a historical NumPy test wheel that was not published for macOS arm64. It still
runs the DEPS-pinned Clang, landmine and revision-metadata hooks required by the
GN/Ninja production build. The pinned `depot_tools` bootstrap is initialized
before use, while those manual hooks use the runner's already resolved Python
binary so PATH changes cannot redirect them through an uninitialized shim.

CI prints the exact output key, hit/miss source and rebuild reason before long
work begins. If a rebuild is necessary, it records `sccache` statistics both
before and after compilation and emits elapsed seconds for toolchain probing,
dependency sync, patching, build hooks, GN generation, V8 compilation,
packaging and validation. The durable V8 package is only about seven MiB when
compressed, so its 90-day artifact fallback is intentionally independent of
the repository's more aggressively evicted Actions-cache quota; a fresh run
renews it before expiry.

The measured device baseline is workflow run `31796177166` (August 2026). Its
V8 build command took 72 minutes 47 seconds after an unrelated
simulator-policy edit invalidated the former whole-script key. `sccache`
processed 2,485 compiler requests, but the newly created namespace produced
2,485 misses and zero hits; it nevertheless retained 2,479 successful object
writes (2,201 at the GitHub level, with six remote write failures) and about
38 MiB locally. This demonstrates that the compiler launcher was active but
that key churn, rather than an absent launcher, caused the expensive cold
build. With the canonical output identity, an unchanged device build restores
the roughly seven-MiB validated package and skips source synchronization, GN,
Ninja and all 2,485 compiler requests. The expected steady-state V8 phase is
therefore artifact/cache download plus validation (normally a few minutes),
instead of the measured 73-minute rebuild. If that complete package is absent,
the stable per-object namespace remains the second recovery layer.

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
