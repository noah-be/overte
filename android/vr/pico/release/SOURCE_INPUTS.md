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
