# Pico finite release batch — source wave33

The existing goal remains paused. This is source integration, not whole feature
parity, native build, physical device or cold-build acceptance.

Account auth-reentrancy, token-import, provider-receiver and persistence-context
v001 are consumed as matching Main/Pico deltas. All coupled AccountManager
header/body and original Application::forceLoginWithTokens changes are present.
The existing Pico setup still installs the protected store before AccountManager.
No Pico copy of the caller is introduced. Existing startup URL/physics fixes in
Application.cpp were preserved, not overwritten with the release snapshot.
Real Qt original-method tests cover the released guards; the Pico source pin
only verifies caller/store selection. Native storage durability, already-emitted
loginComplete actions, same-context ordering, origin/HTTPS and full UI/foreground
recovery remain General/native acceptance work.

Audio device-debug and trace v001 close named diagnostic operands without changing
Pico capture policy, routing or counters. The existing microphone measurement
consumer now expects OVT_REDACTED, not a device name. Independent Android source-ID
checking and the marked measurement window remain mandatory. Capture retrieval
uses the existing fixed relative path, never a path taken from a diagnostic.
Positive mock transcripts use closed operands; obsolete raw level data rejects.
Thirteen shell/mock cases passed, including no-capture readiness, source mismatch,
CSV/capture and cleanup. These are synthetic OS/file boundaries, not microphone
conformance, source identity authentication, capture permission or retention proof.
The helper's historical optional raw capture workflow is not enabled/qualified by
this batch. Raw storage/retention/consent and remaining sinks are still pending.

HTTP diagnostics fixture v001 supplies its exact existing SafeDiagnostics header.
Conan inventory/source-join usage and limitations are in SBOM_PAIR.md. No Shared
schema clone or implicit replacement of candidate evidence was added.

Nine Shared imports are separately mapped DO_NOT_REPLAY in the handoff; General
alone performs remote integration. All prior sealed waves remain immutable.

## Final-check follow-up — source wave34

The final check found sh005-account-persistence-context/v002, source
69791541af09f971f76520a5c96a7152f7a9e5eb, manifest
000579d3df486e9480182ec7f073ba620a071be4c9a883b5616b352f5ff9924d.
Its exact v001 prerequisite was sealed in wave33. All eight released files are
imported together. Direct and network token completion now persist and check
owner/context before loginComplete. Reported read/write failure emits no login
success. This specifically resolves the pre-persistence success issue described
above; it does not undo committed storage after a later successful listener
invalidates context. Native I/O atomicity/reentrancy/durability, settings errors,
same-context ordering, origin/HTTPS and full foreground/UI acceptance stay open.
Four affected original-method Qt tests PASS on the combined stack. Existing Pico
caller/store selection is unchanged; no additional native hook is required.
