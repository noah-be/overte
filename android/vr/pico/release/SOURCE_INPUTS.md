# Pico source input consumer v1

This replaces the Pico Gradle consumer of `common/conan/pico4-debug`,
`runtime-overrides`, compatibility archives and OpenSSL 1.1 aliases. It does
not resolve, fetch, build or repair dependencies. `prepare-deps.sh`,
`build.sh prepare`, `build.sh deps --source-graph` and Gradle all execute the
in-tree `pico-source-inputs.py`. An external adapter is no longer authoritative.
Historical `deps --download` output is not an input to this consumer.

Supply four explicit environment variables:

* `PICO_SOURCE_GRAPH_ROOT`: canonical absolute path to the supplied attempt.
* `PICO_SOURCE_INPUTS`: regular JSON binding file supplied by the input owner.
* `PICO_SOURCE_INPUTS_SHA256`: independently reviewed SHA-256 of that file.
* `PICO_EXPECTED_SOURCE_SHA`: exact 40-character source commit, also required
  to match this checkout's HEAD and both COMPLETE checkpoints.

The binding object has these required fields (paths are relative to graph root):

```json
{
  "contract": "overte-pico-source-inputs-v1",
  "sourceRevision": "<exact source commit>",
  "sourceClosure": "<existing SH009 source closure JSON>",
  "recipeIndex": "<existing recipe export index JSON>",
  "phases": {
    "target": {
      "actualGraph": "<completed target Conan result JSON>",
      "expectedGraph": "<independently pinned target readiness JSON>",
      "checkpoint": "<target.COMPLETE>"
    },
    "host-tools": {
      "actualGraph": "<completed host-tools Conan result JSON>",
      "expectedGraph": "<independently pinned host readiness JSON>",
      "checkpoint": "<host-tools.COMPLETE>"
    }
  },
  "generators": "<target CMakeDeps directory>",
  "qtSourceDirectory": "<patched Qt composition containing qtbase>",
  "qtRuntimePatchSha256": "<SHA-256 of common/conan/patches/qt-pico-android-runtime.patch>",
  "files": {"<each consumed relative file path>": "<SHA-256 of bytes>"}
}
```

The placeholders are documentation, not valid identities. The input owner must
produce and pin the binding from their completed attempt. This consumer never
generates a readiness graph or declares two graphs equivalent. Existing
`provenance/conan_inventory.py` and `conan_sources.py` perform the unchanged
SH009 phase/checkpoint/source-closure joins, retaining recipe/package revisions,
PREVs, source/license metadata and graph hashes. `attempt_root` must match the
explicit root. A claimed Build status is declared metadata, not attestation.

Every file in selected package, generator and Qt source directories must occur
in `files`; empty files and internal symlink payloads hash their actual bytes.
Absolute/traversing paths, escaping symlinks and CMake expansion characters are
rejected. The file binding is checked again after resolution. Supplied inputs
must remain immutable throughout configuration and assembly: these checks do
not provide an atomic filesystem snapshot or authenticate a producer.

Package folders come from actual graph nodes, never a cache search. Required
target selections include qt, openssl, draco and openxr, with unique host context,
Android armv8 Debug/API26 settings. OpenSSL is the existing
`openssl/3.5.8@overte/stable` provider. Only its native `libcrypto_3.so` and
`libssl_3.so` enter staging; conventional linker symlinks are excluded from the
APK. Other legacy/versioned provider payloads and duplicate basenames fail.
Target ELF headers must identify AArch64. Required Qt extraction libraries come
from the actual `qt_dependencies.xml`; QML module metadata and QtAndroid.jar
must exist. CMakeDeps must bind the selected Qt package, and the full generator
bytes are pinned. Generation provenance must still be supplied by the owner.

Host qt, scribe, glslang, spirv-cross and spirv-tools are selected separately
from host-context Linux x86_64 packages. Qt moc/rcc/uic/qmake and the four shader
executables use the selected packages; host Qt must match the target Qt recipe
reference and revision, while retaining its distinct host package identity. All
executables require executable x86_64 ELF headers. The Pico bootstrap passes
their distinct directories through the existing Shared bootstrap; Qt5 imported
tools and AUTOMOC/AUTORCC/AUTOUIC receive explicit host paths across Debug and
RelWithDebInfo. `OVERTE_FDROID_CONAN_DIR` must be unset for this Pico consumer.
For the V2 qualified contract, `uic` is explicitly selected from the target Qt
package: Qt's cross build installs a host x86_64 executable there, while the
headless host profile disables Widgets and does not build `uic`. Its complete
target-package bytes and real producer receipt are bound, and the same executable
x86_64 ELF check applies. V1 retains its original host-package selection.
Conan targets for draco/glad/etc2comp/nvidia-texture-tools must exist; missing
targets cannot fall back to legacy compatibility archives. OpenXR remains an
explicit CMake/AGP target, emits `libplugins_libopenxr.so` directly, and preserves
the existing Android Debug-only E2E layer guard. Native resources must have one
unambiguous result within the current configuration, not the newest other build.

The existing Pico Qt runtime patch must reverse-apply cleanly to the supplied
Qt source. The current Shared Qt recipe does not declare that patch: its owner
must review a source-provider change and regenerate the affected export/lock/
readiness/closure/checkpoint inputs. Patched source bytes alone do not establish
that a Qt binary was built from them. The consumer never patches Qt or rebuilds
it. It must not accept an old patched overlay as a replacement.

Successful resolution is `PICO_INPUT_BYTES_BOUND_NATIVE_VERIFICATION_PENDING`.
It is not complete source parity or permission to build. A separately authorized
native owner must supply/verify the broader Pico graph and toolchains, build the
exact integrated source, and check APK extraction, complete ELF SONAME/NEEDED
closure, unique canonical SSL providers, all PT_LOAD/ZIP 16KiB requirements and
real VR acceptance. The historical Phone APK neither contains nor qualifies the
broader Pico OpenXR output; its previously observed 4KiB alignment remains an
open gate. No build, hardware or distribution operation is performed here.

Host-only checks: `python3 android/vr/pico/tests/test_source_inputs.py` executes
real Python/shell/Java/CMake consumers with explicitly synthetic graph and ELF
fixtures. CMake uses LANGUAGES NONE or script mode, never a native build. Set
`PICO_TEST_GROOVY_CLASSPATH` to explicit Groovy and groovy-json jars and use JDK21
to execute the real Gradle input-resolution Groovy closure without Gradle.

## Qualified local reuse (explicit v2 contract)

`overte-pico-qualified-inputs-v2` retains the v1 payload inventory and consumer
checks and adds original cold phase/source receipts, ordered successful local
build receipts and a separately named `dependencySourceRevision`. It never
rewrites raw Conan Cache/Build/Skip strings. Original cold inputs pass the
unchanged SH009 validator; every reused RREV/package-ID/PREV, recipe/source
identity and transitive dependency identity must match a proven Build origin.
A successful local producer receipt pins its zero exit, network isolation,
readiness, result and complete producer source file map. Later application
commits must retain every producer file byte, including profiles/toolchain,
recipes/exports, source/license locks and composition helpers. The actual
current application SHA remains separately bound by the consumer.

Conan's output-only dependency `skip` flags can differ after a package is
available. All other edge fields and every dependency identity remain checked.
Intermediate unused Skip nodes establish no package origin; final consumed
phases reject Skip. Host/build role changes for identical Linux packages keep
the current graph context and platform checks while matching their actual
producer by package/settings/options identity. No Android package becomes a
Linux host tool through that mapping. Final graph/checkpoint inputs remain
independently pinned; a graph-info result is not a completed build receipt.

This is qualified warm reuse, not a fresh cold build or authenticated external
attestation. Actual immutable payload SHA256, ELF/SONAME/NEEDED/provider/16KiB,
SBOM and runtime acceptance remain mandatory and distinct.

## Separate producer lineages (explicit v3 contract)

`overte-pico-qualified-inputs-v3` keeps the existing payload, Qt/tool/architecture,
consumer and runtime checks. V1 and V2 retain their existing validators unchanged.
V3 additionally requires all three final phases (`bootstrap`, `host-tools`, `target`)
to belong to `dependencySourceRevision`, with actual completed V3 worker receipts.
Old receipts and graph binary states are preserved; transport/restore evidence never
establishes production, and an imported package still needs its original Build origin.

`producerRevisions` maps each full Git revision to `sourceRevision`, `sourceFiles`
and `sourceFilesSha256`. The hash uses UTF-8 JSON with sorted keys, compact separators
and ASCII escaping. Each complete owning producer file map is checked against the
immutable blobs in that exact local Git commit. Only the current producer map is
compared to the current checkout bytes before and after resolution. Historical maps are independently checked;
copying the current map onto an old receipt is rejected. The runtime patch and every
source-ledger/export-index recipe byte are also joined to their own producer map.
This requires the actual historical Git objects locally; a missing object is a failure.

Each `coldOrigins`, ordered `localBuilds` and `phases` entry specifies `sourceRevision`,
`producerSourceFilesSha256`, `phase`, `attemptRoot`, and paths for `sourceClosure`,
`recipeIndex`, `actualGraph`, `expectedGraph` and `checkpoint`. Its `bindings` object
pins the SHA256 of each artifact, independently of the enclosing payload inventory.
Original cold graphs still pass the unchanged SH009 completed Build validator.
Local/final entries additionally pin `receipt`; the receipt must be the original
`overte-pico-local-producer-receipt-v1` for historical production or the new
`overte-pico-local-producer-receipt-v3`. It binds its own producer map, zero exit,
isolated network, jobs and actual/readiness graphs. A completion receipt from a
different source revision or a transport receipt cannot qualify it.

Per-entry `buildConfigurationIds` and `buildConfigurations` retain the original
configuration descriptor names. Each descriptor includes `sourceRevision`,
`sourcePath` (`android/vr/pico/conan/openxr-16k`), `sha256` and `stagedPath`. Both the
original Git blob at that revision and staged bytes must match. The worker receipt
must name exactly the same descriptors. Different historical configurations need
separate entries, rather than replacing their receipt's fields.

New V3 receipts additionally bind `producerSourceFilesSha256`, `checkpointSha256`,
`sourceClosureSha256`, `recipeIndexSha256`, `configurationSha256`, `buildLogSha256`,
`workerExitSha256` and `invocationSha256`. Entry paths and `bindings` must include
`buildLog`, `workerExit` and `invocation`. The actual exit file must contain zero.
The invocation JSON binds the source revision/map hash, phase, attempt root, jobs,
network, zero exit, nonempty command argument list and `configurationSha256` (the
canonical JSON hash of that entry's configuration map). Its `bindings` pins the
actual graph, readiness, checkpoint, source closure, index, build log and exit file.
The receipt then pins that invocation; no circular receipt/self hash is required.
Historical V1 receipts are read without adding these new fields or changing hashes.

Every Cache package recursively joins to a previously proven Build with identical
Ref/RREV, package ID, PREV, settings/options and full dependency edge identities.
Only comparison of otherwise identical Linux/x86_64 packages normalizes `host` and
`build` roles. Current actual context still matches the current readiness exactly;
Android, other architectures and changed dependencies are never normalized.
Transitive child PREVs must also match the original Build. Intermediate unused Skip
nodes establish no origin, and a consumed parent cannot rely on an unproven skipped
child. Final Skip nodes, missing phases, wrong origins and graph cycles are rejected.
Per-graph memoization hashes each dependency subtree once and retains its height;
cycle and 64-node path checks still apply before cached reuse. Evidence is bounded
at 192 cold origins, 256 local builds, 32768 total nodes and 262144 dependency edges.
The final result preserves observed Cache/Build states and names its original
production source, checkpoint and worker receipt where present. It remains byte and
relationship verification, not authenticated producer attestation, a cold build,
current APK qualification or physical device acceptance.

Run `python3 android/vr/pico/tests/test_qualified_reuse_v3.py` for the actual consumer
and validator with temporary real Git histories and explicitly synthetic Conan/ELF
records. It checks map/revision swaps, tampering, original receipt/configuration
bindings, recursive PREV changes, transport confusion and missing final phases.
These test records are not production receipts or native build results.
