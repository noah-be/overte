# SH-004 result binding v001

This release adds an offline acceptance consumer, `tests/device/verify-result.py`,
for the existing runner's run-manifest.json, summary.json and junit.xml. It does
not redesign those formats, perform device work or assert node acceptance.

Invoke with --result-dir, --expected-source-sha, --expected-artifact-sha256,
--expected-adapter, --expected-platform (android/ios/pico4), --required-module
(repeatable exact module IDs), and --device-class (physical/virtual). The adapter
ID must be the actual selected manifest's ID, e.g. appium.android, not a new
invented common adapter. Required module IDs are the reviewed milestone plan,
not the successful subset of a run. Use the included catalog/capability registry.

Producer writes an adjacent result-identity.json with exactly:
contract=overte-sh004-result-v1, sourceRevision (40 lowercase hex), artifactSha256,
runSha256, summarySha256, junitSha256 (64 lowercase hex, exact file bytes).
Bind this to the actual tested candidate at execution time. Adding a sidecar
after the fact without authenticated execution identity is not acceptable proof.
The consumer checks integrity, not producer trust or installation truth.

All required modules must exist exactly once, declare all required operations,
pass with integer-zero returncode and match JUnit. RequireComplete must be true.
Source/artifact/product/device-class mismatches, tampering, skipped/error results,
missing operations, invalid/boolean time or counters and unknown fields fail.
Descriptions must match the pinned catalog. JUnit exports only fixed diagnostic
markers; the included runner patch drops arbitrary system-out text from JUnit.
Do not remove a failure element to make it pass. JSON/XML files are size-bounded;
duplicate JSON keys and XML entities/DTDs are rejected. Output never includes
the rejected payload, target selector, raw exception or file path.

The consumer returns RESULT_BOUND_NOT_NODE_ACCEPTED. It does not scan screenshot
pixels, separate module.log files or authenticate producer/device observations.
Existing artifact privacy audit and downstream retained-output canary scans
remain required. Source/artifact binding hashes are provenance, not device IDs.
All platform capabilities remain unobserved until their actual probes; required
behavior in SH-003 is not an observed capability boolean.

Code prerequisites: included SH-002 terminal_evidence helpers, existing version-1
runner/catalog/capabilities, SH-003 v001 profile semantics. Host tests use a
virtual fixture only and include the real CLI. Full capability-gap classification,
producer emission/verification, artifact/device privacy and original SH-002/003
acceptance remain pending. No hardware admission or complete node claim.
