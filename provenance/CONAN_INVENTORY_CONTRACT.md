# SH-009 completed Conan phase binding

tools/sbom/verify-conan-phase.py is the actual offline caller of
provenance/conan_inventory.py. It reads an already completed phase result,
its original COMPLETE checkpoint, and an independently pinned G3/readiness graph.
The expected source SHA, readiness-graph SHA256, source-closure manifest SHA256
and recipe-index SHA256 are mandatory caller inputs, not inferred from output.

Checkpoint name/source/manifest/index/result-hash must match those independent
inputs and the actual result bytes. Its job count must be1..16 for this qualified
resource profile. Missing/duplicate/extra checkpoint fields, wrong bytes or
symlink leaf files fail. Graph input uses the original SBOM pair's bounded strict
JSON reader (16MiB, no duplicate keys/nonfinite values); there is no network or
binary execution. Hashes are checked again after parsing to catch changed inputs.

Both node-ID sets must match exactly (2..1024 nodes including consumer0), with
canonical numeric IDs. Every dependency edge and the consumer's settings/options/
context match. Each nonroot package matches ref/RREV/package-ID/context/settings/
options/license/dependencies; it declares Build and no remote/binary_remote, and
has actual32-hex RREV/PREV and40-hex package-ID. Recipes restored from a scanned
source export may legitimately be in Conan's recipe cache; this does not admit
binary Cache/Download status. The output includes no cache/build/source paths.

Result status is CONAN_PHASE_BOUND_CONTENT_VERIFICATION_PENDING. These checks
bind declared metadata/checkpoint/readiness; they do not make those inputs an
authenticated source-build attestation or detect forged metadata by themselves.
The independently qualified frozen request, source/lock/license/toolchain gates,
isolated worker/governor logs and real produced binaries remain necessary.
Compiler conf beyond settings/options and checkpoint jobs stays in the original
buildParameters provenance contract. Actual ELF/host-target payload, source
license files, SPDX/CycloneDX component/PURL expansion (including bundled source),
Gradle/toolchain/generated output and full APK identity joins remain pending.

The unchanged SH009 identity API can bind the inventory bytes as package evidence,
but this utility does not silently replace existing raw results or owner callers.
Requires original sh009-identity/v001 and sh009-sbom-pair/v001's JSON reader;
unlike SBOM format validation, this CLI uses standard-library Python only.

Five focused tests use fake declared graphs/checkpoints and the actual network-
isolated CLI. They reject cache/remotes/missing PREV/changed context, locked
recipe/settings/options/license/package ID drift, missing/extra/dangling nodes,
stale source/manifest/index/result, duplicate fields and symlink checkpoints.
Separate real retry07 bootstrap/host-tools original graph/checkpoint comparisons
passed for7 and22 packages; target remains unfinished. No binary reuse occurred.
