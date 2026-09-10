# SH-004 canonical Appium iOS native binding

Implementation-only hook for `tests/device/adapters/ios/binding.py`, owned by
the iOS session. The real Appium entrypoint accepts --native-binding. Use
appium/ios-bound.json for future bound runs, preserving appium-ios identity;
old ios.json remains unbound diagnostics. No device run is authorized here.

Native source implements configure_parser(parser) to ADD its existing candidate
input flags and create_adapter(args, base_class) to validate those inputs and
return a subclass instance of the PROVIDED canonical AppiumAdapter class.
Preserve platform=ios and adapter_id=appium-ios. Do not redefine the Shared
CLI/schema or import a second __main__ class. Candidate flags may precede the
runner-appended action. Shared fields cannot be overwritten by native options.

The same exact native_binding.py as Android binding/v002 loads only the fixed
owned source file, no module-path override or cached target bytecode. Missing or
symlinked binding fails before base construction; no unbound fallback. The real
canonical discover/describe/invoke/cleanup then calls the native subclass.
Native code can override describe/ensure_session/invoke, calling super to retain
existing Appium private target checks, physical attestation and cleanup.
Do not suppress cleanup because a candidate receipt became invalid.

This resolves the actual General-owned describe/native preflight EXTENSION
request, not the still-missing cryptographic installed-iOS identity proof.
Reuse SH002-ios-evidence/v002 and SH009's independently frozen candidate inputs.
The existing preinstalled receipt with cryptographicByteBinding=false, matching
bundle/version, devicectl application inventory or an IPA archive SHA ALONE
cannot produce installedCandidateVerified=true. IPA archive bytes are not the
installed app bundle; do not use an invented direct archive-hash comparison.
Without a reviewed verification mechanism binding actual installed code/signing
identity to the verified candidate, omit executionIdentity or fail bound mode.
The real v003 runner then fails closed. This is a deliberately pending evidence
boundary, not permission to echo expected runner flags or relabel a receipt.

Native implementation can now add real preflight observations and finite failure
behavior in its owned module without modifying General's Appium file. Source
provenance must include that module and its helpers. No arbitrary serials, local
paths, target selectors, URLs or raw errors reach result exports. Bound entrypoint
failures use OVT_APPIUM_ADAPTER_REJECTED; ordinary diagnostic behavior is preserved.

Focused tests execute original Appium parser/module loader/dispatch/entrypoint
with test-only native/OS boundaries. Five positive/negative tests cover action
dispatch, prefix arguments, missing binding without base construction, rejected
Android ambiguity, Shared argument mutation, diagnostics and closed errors.
No test fixture creates an installedCandidateVerified claim for iOS.
Actual native binding, trusted install association, iPad/iPhone form-factor and
telemetry/PID evidence, physical execution and original acceptance remain pending.
