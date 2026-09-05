# SH-005 V8 getter lock/error prerequisite v002

v002 requires v001 and also hardens the actual data() getter. __data remains an
ordinary script property, not private/protected storage. A throwing accessor now
returns undefined with the outer exception intact; terminal failure returns an
empty ScriptValue. Nonobject data() retains its null fallback without asserting
on script-controlled input. No new data lock or lifetime guarantee is introduced.
Ten real-V8 cases now compile both complete original getter functions and pass
in2.033s, covering ordinary/missing/null/throw/termination outcomes for each.

Actual ScriptValueV8Wrapper::property(QString, ResolveFlags) leaked its read
lock when V8 Get failed. This can prevent later release/teardown after a throwing
or terminated getter. The read lock is now scoped by QReadLocker and released
on every Get outcome before wrapping a result. Terminal failure returns an
empty ScriptValue without subsequent V8 diagnostics. Ordinary failed lookup
keeps undefined fallback and one constant diagnostic, with no property name,
object detail conversion or stray x printf. Outer V8 exception handling remains
responsible for the original exception; no new catcher swallows it here.

No native hook or dependency on other v09 source contracts. This is the actual
Shared engine callee needed beneath ScriptManager, not a complete termination
mechanism. Reentrant writes during a getter and general wrapper/isolate lifetime
ownership are unchanged and still require review.

Focused real-V8/Qt regression:

    V8_TEST_ROOT=/explicit/host/node-prefix python3 tests/device/contracts/lifecycle/test_v8_property_lock.py

Compiles the complete original named-property method with real V8/QReadWriteLock,
substituting only engine/value ownership scaffolding. Success, missing property,
null receiver, throwing getter and cross-thread terminated getter all pass.
Every result verifies a write lock can immediately be acquired afterward; raw
captured diagnostics must not contain the canary property name.

Read-only baseline mode V8_PROPERTY_LOCK_BASELINE=14c249d75a6af4ccb71736174508a04fbf3ffc91
fails on both throwing and terminated getters at the write-lock assertion. The
fixed function passes; no user worktree or immutable exports are changed by
baseline mode. Each subprocess has a five-second external timeout. Host V8 is
not a candidate input. No full client/device test or hard production deadline.

Pending: full engine/platform compile, other indexed/data/property/constructor
and native registration paths, lifetime-safe sticky termination/regrant, actual
default-deny informed entity consent and finite revoke, original node gates.
