# Original package transport and restore

`package-store.py` imports an independently pinned original Pico V2 byte binding
into a new private Conan 2.25.2 cache. It performs no dependency or application
build, source download, graph rewrite or producer attestation. Original input
directories, raw graphs, receipts and manifests remain read-only.

`inspect` verifies the binding digest and its original graph/index bytes before
reporting metadata availability. Its selection output is a candidate that must
be independently reviewed and SHA256-pinned before `restore`. Availability alone
does not verify package contents. Missing identities are explicit; selecting a
subset never qualifies the full dependency graph.

Both commands require explicit `--binding`, `--expected-binding-sha256`,
`--evidence-root`, one or more `--payload-root` directories and `--recipe-root`.
The evidence root contains the original bound graphs and index. Each payload
root uses the same relative `conan/p/...` layout recorded in those graphs.
Recipe exports come from the original index's validated `export` and
`export_sources` directories, including unchanged recipe manifests and RREVs.

Restore additionally requires `--selection`, `--expected-selection-sha256`,
`--cache`, `--transport` and `--receipt`. All output paths must be absolute and
canonical; the cache must be new and private, and every output must be outside
the immutable input roots. Existing outputs are never overwritten. A partial
new transport/cache after failure remains unqualified and requires inspection
before any cleanup or retry.

Before writing the transport, the importer checks selected original graph
identities, exact package file sets, manifest content hashes, original PREVs,
SHA1 package IDs from `conaninfo.txt`, available original SHA256 inventory
entries, complete recipe SHA256 ledgers and recipe RREVs. Existing MD5/SHA1
values are Conan's legacy identity format; they are not a replacement for the
independently pinned binding and new SHA256 transport ledger. Symlink targets
must remain within their package, special files and privileged modes fail, and
duplicate identities, JSON keys, paths and manifest entries fail. Limits are
100,000 transport entries, 32 GiB uncompressed bytes, 32 MiB metadata per file,
64 recipes and 128 selected packages. Source bytes are rechecked while writing.

The new archive uses the existing recipe transport layout and Conan's actual
`cache restore` command. The new cache has no configured remotes. Actual Conan
listing must match the selected RREV/package-ID/PREV set exactly, and actual
`cache check-integrity` must succeed before a receipt can report
`TRANSPORT_RESTORE_COMPLETE`. The receipt includes input/selection/graph/archive
digests, a SHA256 transport inventory and original CLI output. Its qualification
explicitly remains `NOT_DEPENDENCY_PRODUCTION_OR_APPLICATION_QUALIFICATION`.
It is a newly recorded import, not a historical producer receipt or cold build.

Conan `finalize()` can expose a mutable `f/` directory with contents distinct
from the immutable `p/` package. Only the original immutable package whose
manifest defines PREV is importable. The historical Meson 1.10.2 and 1.6.0
finalize paths have no available immutable package in the inspected payloads;
they need a genuine original backup or separately scheduled source packaging.
Do not relabel a finalized directory or force a newly produced PREV to match.
The metadata-available NASM 2.15.05 payload contains foreign PCRE2 files outside
its original manifest in the inspected historical attempt. Its whole-tree import
is rejected; the importer never silently strips those files or changes originals.

After import, actual offline readiness/install from the final frozen sources,
complete source/license/toolchain evidence, missing-package production and the
Pico owner's separate V3 producer lineage are still required. Raw Cache/Build/
Skip states and original producer source maps remain unchanged. Current source
invocations and their own maps must be separate from historical production.

`python3 android/common/conan/test_package_store.py` requires real Conan 2.25.2,
an actual C++ compiler and `ar`. It compiles a small host static library with an
explicit private profile, records its actual Conan-produced package, restores
it into another empty private cache, installs offline with `--build=never`, then
links and executes the real restored library. Altered manifests, valid-but-
foreign PREVs/package IDs, recipe/byte ledgers, path/symlink escapes, finalize
paths, duplicate metadata, budgets, special files and late changes fail. These
host tests do not qualify original Overte packages, a full APK or any device.
The fixture records the actual local compiler version, extending only its own
private test settings when the Conan preset predates that compiler.
