# Script VM interruption

`ScriptManager::stop` immediately invalidates the load scope and retains its
engine while requesting `abortEvaluation`, before dispatching manager-thread
shutdown. `ScriptEngineV8::abortEvaluation` calls V8 `TerminateExecution` without
a V8 scope or Locker. V8 explicitly allows this call from another thread; taking
the Locker would wait behind the running evaluation. The engine/isolate are
initialized in their constructors and are not replaced during a live manager's
lifetime. Callers must own a live manager, as required by the existing stop API.

The focused test compiles both complete production method bodies and executes
them against real host V8 and Qt. An actual JavaScript callback announces entry,
then JavaScript runs indefinitely. The manager's target event loop is held until
the VM returns. Single and duplicate stops interrupt the VM within the test's
one-second bound before queued manager delivery; delivery emits one state change.
Ordinary arithmetic still completes. Engine construction, signal receivers and
destruction are explicit seams. This is not a full ScriptManager/native build.

The baseline failed both stop cases at the bounded wait for VM exit. The existing
load-diagnostics test retains its stopped/stale/duplicate completion assertions
and compiled delayed-invalidation negative. Its engine is a named execution seam;
VM behavior is checked separately by this test.

Run with `V8_TEST_ROOT` pointing to an existing compatible host V8 tool prefix:
`python3 -B tests/device/contracts/lifecycle/test_script_vm_stop.py`.
The local review used the previously extracted Node 22.23.1 host test library,
not the source-locked 22.22.3 Android/iOS candidate dependency. No candidate ABI,
JITless or hardware acceptance follows from that fixture.

This changes stop into an interruption request, including script-requested stop.
JavaScript following that request is not guaranteed to run. Native cleanup must
not depend on JavaScript finally/ending callbacks completing. V8 termination can
unwind JavaScript but cannot forcibly bound a native callback, resource-cache
abort, signal teardown, or destruction. Later evaluations/ending handlers and
complete manager teardown require separate bounded-revocation work. There is no
consent grant API added here: remote entity scripts remain default-denied. This
closes the empty VM-abort implementation, not SH-005 acceptance or finite revoke.

## Persistent admission after interruption

The engine now owns an atomic abort latch. `abortEvaluation` sets it before
requesting V8 termination; it never resets for that engine lifetime. This matches
the production stop caller, which does not restart a stopped manager. All three
direct evaluation overloads, both call/construct overload pairs and the actual
Qt signal meta-call entry check the latch before engine work. Signal dispatch
also checks it between callbacks. V8's transient terminating state alone cannot
represent permanent manager stop after an evaluation has unwound.

The original invocation fixture additionally compiles the complete production
String evaluation method. Ordinary arithmetic succeeds first. Then the actual
abort method runs, the test deliberately cancels V8's transient termination,
and late evaluation/call/construct must return empty without running JavaScript,
converting arguments or notifying error receivers. The real Qt/moc signal test
does the same and requires zero callbacks/conversions. The atomic field, getter
and abort method are extracted verbatim from current production source/header;
engine construction/value ownership and diagnostic receivers remain seams.
Existing throwing, termination, argument-boundary and lock-release cases remain.

Controlled negative runs retain the current latch/abort implementation but
compile the preceding entry bodies via `OVERTE_ABORT_ADMISSION_BASELINE`.
They fail specifically on late String evaluation and signal callback delivery,
showing that V8 cancellation alone does not enforce admission. Program/closure
overload admission is source-reviewed, not a full runtime proof of those bodies.
This is still not a full-header, native/JITless or finite-revocation proof:
property/proxy/conversion side effects and native resource/callback teardown
need separate review. The deny-by-default entity consent fence stays intact.
