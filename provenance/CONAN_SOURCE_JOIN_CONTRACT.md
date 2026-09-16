# Completed Conan phase to source ledger

SH-009, cohort #685. Prerequisite sh009-conan-inventory/v001
93a754a6be02cc30d13ca79aba2e434f6db7b34b, manifest
c259a7cc6edf59b3f337609e27745e637b8278ccbe20a1599a54b73127c43607,
and its exact sh009-sbom-pair/v001 / sh009-identity/v001 prerequisites.

Run `python tools/sbom/join-conan-sources.py` with the original verify-conan-phase
arguments plus `--source-closure PATH`. All expected digests/source SHA remain
mandatory independent inputs. The CLI reruns the original completed checkpoint
and readiness graph validator itself; it does not trust a supplied inventory
JSON file as proof of those checks. Then it matches source-ledger bytes to the
independently expected closure SHA before and after bounded parsing.

Every resulting package must match exactly one source-ledger reference/RREV and
the relevant phase. Duplicate references, missing packages, wrong phase/RREV,
inconsistent recipe-index/main-recipe digests, invalid relative paths, missing
source/licensing identities and inconsistent source/system classifications reject.
Each source-bearing package carries its explicit source object SHA, canonical
HTTPS URL, license path and license-file SHA; multi-source Qt is not collapsed
into one archive. Virtual system packages remain separately classified and
require their explicit provider and toolchain hash, never an invented archive.
Existing package ID/PREV/settings/options/Conan context/dependency fields survive.
The ledger can include other phases; it is not incorrectly required to contain
only the completed phase's subset.

Limits: bounded16MiB strict JSON,1024 nodes/packages,128 sources per package,
4096 recipe file records,8192-character source URL and1024-character license label.
Source paths are metadata only and never opened/executed by this join. No cache,
build directory or environment is copied into the result. Original public recipe
relative paths and declared canonical source URLs are retained intentionally.

Important: `declaredLicenseLabel` preserves the ledger's literal `spdx` field.
It is NOT asserted to be a syntactically valid SPDX license expression or legal
conclusion. The actual libnode ledger says `MIT plus bundled notices`; a complete
SBOM must resolve bundled notices and LicenseRef definitions using their real
license texts. This tool never silently rewrites that into MIT or infers AND/OR.

Success is `CONAN_SOURCE_METADATA_BOUND_PAYLOAD_VERIFICATION_PENDING`.
This is metadata binding, not an independent attestation that source archives,
recipe bytes or license text were physically used. Required prior source-store,
recipe/toolchain/network/cache checks remain separate. Actual archive/license
bytes, bundled third parties, generated/Gradle/toolchain inputs, binary/ELF/APK
completeness and full SPDX/CycloneDX/node acceptance remain required.

Focused tests use declared synthetic inputs, actual offline CLI, mismatched
source digests, recipe revision/context/index drift, virtual-provider omission,
duplicates and path/identity negatives. Real retry07 completed bootstrap and
host-tools inputs are separately exercised outside the immutable build checkout;
no unfinished target output is accepted.
