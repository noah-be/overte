# SH-005 checked engine string factories v001

Three complete actual ScriptEngineV8::newValue overloads now preserve their
input encoding and explicit length: QString uses UTF16 code units, QLatin1String
uses one-byte Latin1, and const char* keeps its existing NUL-terminated UTF8
contract. Explicit QString/Latin1 embedded NUL and bounded nonterminated Latin1
views no longer truncate/overread; Latin1 high bytes no longer become UTF8
replacement characters. Lone UTF16 surrogate code units remain intact.

V8 MaybeLocal results are checked instead of ToLocalChecked. Lengths exceeding
V8 kMaxLength and null C-string pointers return an invalid ScriptValue, never a
partially initialized wrapper. Null/empty QString or Latin1 values produce empty
strings. C-string callers still own pointer validity and termination. This is
not recovery from process-level OOM, arbitrary native pointers, inactive isolate
lifetime or a sticky cancellation/revocation guarantee.

All3 COMPLETE original functions compile/run against real host V8/Qt with
QT_NO_DEBUG. Fourteen encoding/length/null cases pass; engine/context/value
ownership storage is an explicit fixture boundary. Baseline b71f7f9f25 readonly
RED reproduces QString embedded-NUL truncation at the real V8 string length
assertion. No baseline crash is needed to claim the null-pointer guard.

No new native hook or code-level prerequisite beyond existing engine wrappers.
Use V8_TEST_ROOT pointing at host-only Node22.23.1 test tools, not candidate
Node22.22.3. Full engine/Qt5/native builds, allocation-failure injection, actual
consent grant/finite revoke and original SH005 acceptance remain pending.
