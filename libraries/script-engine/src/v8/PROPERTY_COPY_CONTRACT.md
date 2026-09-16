# SH-005 checked V8 property-copy prerequisite v002

v002 requires unchanged v001 and replaces the actual Script.require transfer
block with copyRequireProperties. Source/destination Script and require objects
are validated before casting; callable require objects remain supported. Getter
failures, missing/malformed objects, cache enumeration/copy errors and termination
discard the closure context with a balanced evaluation counter. No debug-only
assertions or QString exception path substitutes for validation here.

The original seven tests plus eight real-V8 require cases pass in1.959s including
compilation. Added cases exercise callable cache success, each malformed object
boundary, source getter/cache getter errors and termination inside cache getter.
An initial malformed JavaScript termination fixture lacked a closing brace and
failed during test setup; corrected fixture compiles and tests the intended
actual helper. This was not a candidate build or production-runtime result.

Requires sh005-v8-diagnostics/v001 (v002 recommended for the compiler caller).
This narrow Shared V8 implementation is the actual callee beneath ScriptManager;
its unchecked failure paths must be repaired before the backlog's in-flight
entity-script revocation can safely use V8 termination. No native hook or new
cross-platform consent API. This release does not wire abortEvaluation.

copyEnumerableProperties preserves the former enumerable-property semantics,
including inherited properties, accessors and destination setters. Each V8
Maybe/MaybeLocal is checked. Enumeration/getter/setter exceptions or termination
return false immediately; null context/object handles also fail closed. It does
not avoid executing getters or impose a production timeout. Caller owns TryCatch
and must discard partial destination contents rather than publish them.

The actual storeGlobalObjectContents caller now returns bool and publishes its
snapshot/cache flag only after a complete successful copy. Failed setup records
an exception and stops evaluateInClosure with a balanced evaluation counter.
The two actual global/closure property loops use this helper and discard the
new closure context on failure. Unused diagnostic object traversal and an unused
closure.global getter evaluation are removed; they previously ran before the
guarded copy. Compile-error exit now also balances the evaluation counter.

Focused real-V8 test:

    V8_TEST_ROOT=/explicit/host/node-prefix python3 tests/device/contracts/lifecycle/test_v8_property_copy.py

Seven network-isolated subprocess cases, each with a five-second external
timeout, compiled and passed in1.687s. Actual helper and complete original global
snapshot function cover inherited/own success, getter/proxy/setter throw,
cross-thread termination inside a getter, successful cached snapshot, and failed
snapshot remaining unpublished followed by successful clean retry. Only engine
error notification is substituted in the snapshot harness. Full evaluateInClosure
is not compiled by this focused test. Host Node22.23.1/V8 is test-only, never a
candidate input or pinned toolchain replacement.

Still pending: registration, constructor/property and
native callback paths; sticky revocation, lifetime-safe termination, regrant on
a fresh isolate; actual default-deny fetch/compile/run consent and informed UI;
whole script-engine/platform build and finite device acceptance. No claim of
safe arbitrary hostile scripts, hard execution deadline or SH-005 PASS.
