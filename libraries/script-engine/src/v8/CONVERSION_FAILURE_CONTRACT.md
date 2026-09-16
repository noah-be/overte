# V8 coercion/comparison failure boundary (SH-005 prerequisite)

Actual numeric conversions no longer assert then dereference an empty V8 result
when user valueOf/Symbol.toPrimitive throws or is terminated. Integer/unsigned
failure returns0; number failure returnsNaN. Existing caller TryCatch retains
the exception. toInt32 uses V8's signed32 conversion, including modulo behavior,
instead of narrowing an arbitrary integer in C++. Successful conversions retain
their expected values. Empty handles also fail safely.

toString checks explicit ToString before reading UTF8, propagates coercion errors
and preserves embedded NUL with explicit length. getPropertyNames checks each
key/conversion and discards partial output on failure, preserving numeric key
conversion, order and embedded-NUL names. It still uses the original enumerable
property semantics; it is not a snapshot or bounded-time user-code operation.

equals invokes V8 Equals exactly ONCE. Previously it invoked once to test
IsNothing then again for FromJust: a side-effecting second coercion could throw
and abort. Missing and cross-isolate operands now returnfalse before dereference;
strictlyEquals receives the same runtime guard. No new cross-engine coercion.

Nine COMPLETE original functions are compiled with real V8/Qt and QT_NO_DEBUG;
43 isolated cases test numeric/string/key success, throw, termination, empty,
signed/unsigned wrap, embedded NUL, equality single coercion and missing/cross-
isolate operands. Only engine/value ownership storage is a test boundary.
Optional V8_CONVERSION_BASELINE performs a read-only single-coercion RED check;
disable core dumps before invoking that deliberately failing historical case.
General's read-only baseline0abecb2d reproduces Fatal error in v8::FromJust /
Maybe value is Nothing (child return-5, no core); the fixed43-case run passes.

Host-only Node22.23.1 tooling is not the F-Droid candidate's Node22.22.3. Full
engine/platform compilation, repr traversal, native/proxy callback lifetime,
sticky cancellation, finite revoke, consent grant and artifact/device gates
remain pending. No runtime deadline follows from a terminated test process.
