# SH-009 byte/input identity v001

Functional artifact binding slice, not package/SBOM/signature acceptance.
`provenance/artifact_identity.py` exposes normalized_inputs, digest_file,
read_record and validate. Its production consumer is
`tools/sbom/verify-artifact-identity.py`, an offline CLI usable by all owners.
No network, signing, upload, build or device operation occurs.

The closed record fields and exact CLI flags are defined in the source. Bind
the actual candidate bytes, sourceRevision, product, monotonic versionCode and
channel. Source-proof/internal-candidate/fdroid-candidate are workflow labels,
not authorization for publication. Expected source and input map must come from
the independently frozen build request, not be copied from untrusted output.

Normalized input labels are sourceTree (SHA256 of the archived source tree),
sourceClosure, recipes, bootstrapLock, hostLock, targetLock, toolchain and
buildParameters. Each is SHA256 of its exact pinned content; buildParameters
contains all effective flags/profile/version parameters and the job plan. The
normalizer sorts these labels and hashes compact JSON; cold/warm comparison
must use identical effective inputs. Do not strip a meaningful flag merely to
obtain equality. No private absolute paths or timestamps are part of this map.

Evidence binds six exact files: bootstrapPackages, hostPackages, targetPackages,
generatedOutputs, spdx and cyclonedx. Package inventories must later contain
actual host/target Conan recipe/package revisions from completed graph results;
generatedOutputs must account for packaged generated resources and binaries.
This v001 verifies their byte binding, NOT their semantic completeness. Empty,
missing, symlinked, foreign or changed bytes fail. A filename is never treated
as proof of file content. No binary cache from this utility enters a build.

SPDX/CycloneDX are distinct evidence documents; semantic/schema/completeness
validation and joining their component inventories to actual binary payloads
remain required. Their primary format references are
[SPDX 2.3](https://spdx.github.io/spdx-spec/v2.3/document-creation-information/)
and [CycloneDX 1.6 schema](https://raw.githubusercontent.com/CycloneDX/specification/1.6/schema/bom-1.6.schema.json).
This utility does not claim that a hash check implements either standard.

Signature and upgrade states in this slice are pending, or explicitly not-
applicable-source-proof only for source-proof. Self-declared verified states
are rejected. Native signature/entitlement checks and authorized upgrade
receipts must be integrated in a later version; source proof is not a signed
candidate. Version codes at/below the independently supplied minimum fail.
Tag/version/channel mapping, complete SBOM/CVE checks, generated payloads,
SH-001/002/010 acceptance and downstream upgrade proof remain pending.

Run tests/device/schema/artifact-identity/test_identity.py. Five host test methods
cover actual CLI, stable normalization, source/toolchain/version mismatch,
foreign/missing bytes, bogus verification claims, duplicate JSON and symlinks.
Dummy bytes are explicitly test-only, not an APK fixture or native package proof.
Success text is ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING. Consumers must retain
that distinction and combine with SH-002 mandatory tiers and native verification.
