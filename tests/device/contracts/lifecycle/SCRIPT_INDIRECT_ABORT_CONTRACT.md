# Indirect JavaScript admission after stop

Prerequisite: the engine-owned atomic abort latch and real VM interruption.
ScriptValueV8Wrapper now checks that latch before data/named/indexed property
reads, property tests/names, prototype access, data/property/prototype writes,
numeric/string coercion, loose equality, variant/QObject conversion and repr.
Rejected operations return the existing empty/false/zero/NaN failure shape or
perform no write. Pure type queries, strict equality and native value release
remain available; those do not invoke JavaScript coercion.

The actual iterator constructor rejects before enumerating properties. Existing
iterators stop advancing and return empty names/undefined values after abort,
so a previously captured object cannot invoke a later getter. The outer iterator
still exists and keeps its existing pointer contract; no null iterator is handed
to callers that expect an object. Destructor handle release remains enabled.

Direct ScriptEngineV8::castValueToVariant also rejects at its own boundary and
clears the output, since native callers can bypass ScriptValueV8Wrapper. This
engine entry and wrapper variant/QObject/repr gates are source-reviewed; the
complete conversion/representation implementations are not runtime-proven by
the fixtures below. Inverse/native custom marshalling remains further work.

The existing host fixtures compile nine complete original property/write methods,
the original scalar/coercion/name methods, and the complete V8 iterator class.
Real V8 getters, setters, proxy traps and Symbol.toPrimitive callbacks are used.
After the actual abort method, tests explicitly cancel V8's transient termination
and require that no callback executes. New and previously advanced iterators are
both covered. Ordinary, throw/termination, exact values, argument context and
lock-release checks remain. The expanded real-method compile exposed an existing
Qt6-invalid QString(arrayIndex) diagnostic; QString::number now preserves the
intended decimal index and compiles on the host.

OVERTE_ABORT_ADMISSION_MUTATION=1 removes only the admission lines in test
scratch, keeping the unrelated Qt correction and current real abort latch. All
three fixture programs then fail at the late callback/value assertions. This is
a controlled compiled negative, not a production bypass or a relaxed assertion.

Host V8 is the existing Node22.23.1 test tool, not the target22.22.3 source-locked
runtime. Engine construction/value ownership are explicit seams. Full headers,
native/JITless builds, already-entered callbacks, inverse/custom marshalling,
ScriptManager stop-before-run completion, full teardown and informed consent/
finite revoke remain unaccepted. Remote entity scripts remain denied.
