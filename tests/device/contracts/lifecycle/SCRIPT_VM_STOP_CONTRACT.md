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
