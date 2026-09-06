# SH-009 SPDX/CycloneDX pair validation

The actual offline tools/sbom/verify-sbom-pair.py consumer uses
provenance/sbom_validation.py. Existing artifact_identity.py and owner callers
are unchanged. It requires independently supplied expected-source-sha and
expected-artifact-sha256; neither is inferred from the two SBOMs themselves.

Use official spdx-tools0.8.5's full SPDX2.3 model validation and
cyclonedx-python-lib11.12.0[json-validation]'s strict CycloneDX1.6 schema validator.
The latter resolves its included schemas locally. Missing validators fail closed;
there is no online schema fallback or validation-skipping switch. Tests execute
with network unshared. Tool installation is outside every Cold Build input/cache.

This first admitted profile is flat package-level data, not every optional shape
in either standard. SPDX document/package keys are restricted as specified in
the implementation, filesAnalyzed must be false; file/snippet/external-document
and nested/pedigree component profiles are not supported. Input is at most16MiB,
4096 total packages,65536 relationships; duplicate keys/nonfinite JSON/symlink
leaf files and inconsistent/duplicate identifiers fail. Package sets match by
unique PURL, name, version and declared license. Dependencies match by package
identity, include every CycloneDX component, and reach every package from root.
PURLs must be canonical per pinned packageurl-python, with matching name/version;
even agreeing documents cannot contradict their own PURL identity. CycloneDX
top-level services/compositions/formulation and other non-package profiles are
rejected, not silently skipped. The pinned validator dependency set is in
tools/sbom/requirements-validation.txt; install only into a separate tool venv.
Unknown SPDX top-level/package fields are rejected before the official parser
can silently discard them. This is a constrained profile, not a general SBOM
format converter or all-extension validator.

One SPDX document DESCRIBES one root package; its PURL matches CycloneDX's
metadata.component. Both root SHA256 values equal the independent artifact hash.
SPDX root sourceInfo is exactly overte-source-revision:<SHA40>, and the root
CycloneDX property overte:sourceRevision must contain that same independent SHA.
Only package DEPENDS_ON relationships are currently admitted. Build-versus-
runtime context still needs explicit reviewed component identity/inventory input.

Success is SBOM_PAIR_VALID_CONTENT_VERIFICATION_PENDING. Two mutually consistent
documents can both omit/misdescribe real dependencies: actual completed Conan
RREVs/PREVs/host-target settings, source/license closure, Qt bundled components,
generated outputs, Gradle/toolchain inventory and packaged APK/ELF bytes must
still be joined. The supplied source label is not a cryptographic proof that
the APK was built from that source. Use the original SH009 identity and SH002
independent-input gates plus real candidate receipts; no node acceptance or
complete SBOM/CVE/license-compliance claim is emitted by this utility.

Tests use explicitly fake, format-valid package documents, not a real APK. They
exercise both official validators and the original CLI; wrong fields/versions,
packages/licenses/PURLs/root/source/artifact/dependencies/orphans/duplicates,
bounded input collections and closed error output fail. Detailed parser messages
are never returned by the CLI. Full stderr/logging/privacy coverage remains part
of retained producer/output verification.

Primary specifications and tool APIs inspected for this implementation:

- https://spdx.github.io/spdx-spec/v2.3/document-creation-information/
- https://raw.githubusercontent.com/CycloneDX/specification/1.6/schema/bom-1.6.schema.json
- https://github.com/spdx/tools-python
- https://github.com/CycloneDX/cyclonedx-python-lib
