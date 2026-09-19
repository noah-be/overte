# Pico offline SBOM pair consumer

Consume sh009-sbom-pair/v001 source 4cee7e15b010133901cd13a43dbb971721b34789,
manifest 781c58dff5aba47b76ab52e50ceb5530956bd8b8d41876b7d6fe017b4d01753e.
The existing sh009-identity/v001 prerequisite is already imported. No native
caller or candidate verifier policy is replaced.

From this worktree, explicitly invoke the released offline CLI using an isolated
validation-tool environment with all36 requirements-validation.txt pins:

```sh
python tools/sbom/verify-sbom-pair.py \
  --spdx /absolute/path/to/pico.spdx.json \
  --cyclonedx /absolute/path/to/pico.cdx.json \
  --expected-source-sha REVIEWED_SOURCE_SHA40 \
  --expected-artifact-sha256 INDEPENDENT_APK_SHA256
```

These paths and identities are placeholders, not available/accepted artifacts.
Supply independently reviewed candidate identities; do not copy expected values
from the documents under test. Missing validators or failed validation reject.
Do not run this as a substitute for the original native/build/evidence gates.

Eight original API/actual network-isolated CLI tests PASS4.554s. All five exported
files matched released bytes. The existing General isolated validation-tool venv
was read-only reused with Python bytecode writes disabled; all36 installed versions
match pins and both install-report/observed-requirements hashes match RELEASE.json.
No package installation, native build, network mutation or real candidate claim.
The previous diagnostic label ALL_37_VALIDATOR_PINS_MATCH counted the comment
line incorrectly; actual assertion checked every pin, and the file has36 pins.

Success remains SBOM_PAIR_VALID_CONTENT_VERIFICATION_PENDING: both documents may
omit the same real dependencies. Actual Conan RREV/PREV/settings, license/source/
Qt/Gradle/toolchain/generated inputs and APK/ELF content joins remain pending.
No full SBOM completeness, license/CVE compliance or PI-002/SH-009 PASS is claimed.

## Completed Conan phase/source metadata (batch wave33)

Consume sh009-conan-inventory/v001 (93a754a6be02cc30d13ca79aba2e434f6db7b34b)
and sh009-conan-source-join/v001 (856af70b24cd7b52f5983ad135e855595057334f).
Both original CLIs now exist in this Pico worktree. They use standard-library
Python and the already consumed strict JSON reader; no validator installation,
Conan invocation or build-worker input mutation is needed.

For a separately authorized, already COMPLETE phase, use the original caller:

```sh
python3 tools/sbom/join-conan-sources.py \
  --actual-graph /absolute/path/to/completed-result.json \
  --expected-graph /absolute/path/to/independently-pinned-readiness.json \
  --checkpoint /absolute/path/to/target.COMPLETE \
  --phase target \
  --expected-source-sha REVIEWED_SOURCE_SHA40 \
  --expected-graph-sha256 INDEPENDENT_READINESS_SHA256 \
  --expected-manifest-sha256 INDEPENDENT_SOURCE_CLOSURE_SHA256 \
  --expected-recipe-index-sha256 INDEPENDENT_RECIPE_INDEX_SHA256 \
  --source-closure /absolute/path/to/source-closure.json
```

Placeholders are not accepted artifacts. For phase-only binding use
tools/sbom/verify-conan-phase.py with the same arguments except --source-closure.
Do not manufacture COMPLETE checkpoints or derive expected identities from the
untrusted result. The join reruns phase validation, rather than trusting an
intermediate JSON inventory. Existing candidate/SH002/SH009 checks remain required.

Nine synthetic offline CLI/API tests passed in this batch. No real build result
was inspected or credited. Success is respectively
CONAN_PHASE_BOUND_CONTENT_VERIFICATION_PENDING or
CONAN_SOURCE_METADATA_BOUND_PAYLOAD_VERIFICATION_PENDING. Declared license labels
are not validated SPDX expressions. Source/license/archive physical bytes,
bundled components, toolchain/Gradle/generated inputs, real binary completeness
and APK identity joins remain open. This narrows metadata gaps above only.
