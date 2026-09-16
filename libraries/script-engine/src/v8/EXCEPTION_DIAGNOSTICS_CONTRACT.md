# SH-005 V8 diagnostic safety prerequisite v002

v002 adds the actual ScriptProgramV8Wrapper::compile error path to the same
captured-metadata reader. Syntax diagnostics no longer invoke exception.stack
or arbitrary exception coercion. The syntax-result constructor now retains its
already-declared errorBacktrace argument (previously silently discarded).
Apply v002 after immutable v001; no native migration hook. The focused test now
also compiles that complete original compile function and original syntax-result
class, using only test substitutions for engine storage. Real V8 validates valid,
cached and invalid source, with hostile prepareStackTrace untouched. Original
six diagnostic scenarios still pass; the combined check took 2.021 seconds.

This is a functional Shared error-path repair, NOT entity-script consent or
finite revocation. No TerminateExecution caller, timeout, stop/restart policy or
native platform API is introduced. In particular abortEvaluation remains
unimplemented: do not wire cancellation based only on this release.

V8ExceptionDiagnostics.h reads captured Message/StackTrace metadata without
coercing arbitrary resource names, exceptions or exception.stack. Missing
metadata has a constant message, empty filename/stack and line/column -1.
Termination returns only a fixed diagnostic; no CancelTerminateExecution occurs.
Captured stacks are bounded to 32 frames. Custom Error.prepareStackTrace output
is intentionally no longer evaluated for diagnostics.

Actual Shared callers are getFileNameFromTryCatch, formatErrorMessageFromTryCatch
and setUncaughtException in ScriptEngineV8.cpp. Runtime exception storage avoids
wrapping an empty/terminal exception and avoids emitting exception callbacks for
termination. Both evaluation overloads check absent Message before dereference;
compile/run/closure-run/function-call terminal returns avoid the normal error
callbacks and backtrace path. Maybe line/column results use fallback values.
Normal nonterminal exceptions still retain their thrown value when available.

Phone/Pico/iOS consume unchanged Shared source; no native hook and no competing
consent schema. This delta has no code prerequisite on another v09 contract.
Its base commit is a source pin, not a prerequisite to unrelated evidence code.

Focused check:

    V8_TEST_ROOT=/explicit/host/node-prefix python3 tests/device/contracts/lifecycle/test_v8_exception_diagnostics.py

Compiles the actual helper plus two complete original diagnostic caller functions
with real Qt and V8. Six isolated subprocess cases cover normal throws, disabled
message capture, no exception, hostile stack getters, hostile prepareStackTrace
and cross-thread TerminateExecution of infinite JS including a JS catch clause.
Each execution has a five-second external timeout; the observed pass is NOT a
production stop deadline. Host Node22/V8 library is a test tool, not an approved
candidate binary input. Tests never contact a device or network.

Still pending: whole script-engine Qt5/Qt6/platform compilation, remaining
closure/global/property/constructor ToLocalChecked paths, engine/isolate lifetime
and cross-thread stop ownership, sticky revoked state and fresh-isolate regrant,
default-deny fetch/compile/evaluation consent gates and real informed UI, unload
and native callback handling, finite in-flight revoke proof and all original
artifact/device acceptance. No statement that arbitrary hostile JS is now safe.
