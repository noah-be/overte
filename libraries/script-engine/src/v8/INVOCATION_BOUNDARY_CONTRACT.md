# Checked V8 list invocation boundary (SH-005 prerequisite)

Actual ScriptValueV8Wrapper list call/construct now check the fixed Qt argument
capacity at runtime BEFORE argument conversion/array writes, including release
builds. Empty/non-function receivers fail with the existing undefined fallback;
construct additionally rejects non-constructible functions such as arrows.
The same maximum Qt argument count is preserved; no API expansion is implied.

Empty or terminated argument conversion returns an empty ScriptValue, without
entering V8 with empty handles. Call/construct lock scopes use QReadLocker and
release before return/error processing. Constructor termination returns empty
before any diagnostic work; ordinary constructor exceptions still propagate to
the caller's existing TryCatch. Existing call diagnostics remain unchanged.

Focused test compiles both COMPLETE original functions with real V8/Qt locks
and QT_NO_DEBUG, not just a rewritten model. Sixteen isolated cases cover zero,
capacity, capacity+1, wrong receiver type, throw, terminate, empty conversion
and arrow call/construct. Manager/context diagnostic receivers, ownership and
cross-engine conversion are explicit substitutes. This is NOT full wrapper
lifetime safety, a sticky cancellation backend, finite native stop, informed
consent functionality or candidate/platform compilation proof. The ScriptValue
arguments-object overloads remain their prior unimplemented paths.
