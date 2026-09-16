# SH005 native QObject method dispatch

The complete `ScriptMethodV8Proxy::call` refuses stopped engines, rechecks
admission after conversions and before native invocation, and discards return
processing after a native method stops its engine. It holds the target as a
QPointer, so a converter that deletes the QObject prevents later invocation.
These checks cover synchronous reentry; they are not a general cross-thread
QObject lifetime guarantee and cannot interrupt a native method already running.

Generic Qt invocation retains pointers to argument values. Both per-overload
backing lists now reserve capacity before appending values, preserving addresses
on Qt6. Argument and ScriptValue return descriptors use explicit QGeneric types,
which avoid the newer Q_ARG/Q_RETURN_ARG template overloads changing the intended
legacy ten-argument dispatch. QVariant return storage keeps separate Qt5/Qt6
constructors. More than ten admitted arguments is refused before indexing.

The focused host test compiles the complete production call method and executes
real V8 Function callbacks and real Qt/moc Target methods. Cases include a
correct two-argument result, void and ScriptValue results, stopped entry,
converter-triggered stop, converter deletion of the target, and native-triggered
stop. Engine conversion/context stacks and ScriptValue handle storage remain
explicit seams. Removing only admission lines from the compiled method retains
Qt compatibility fixes and causes forbidden native invocation/return conversion.
Initial full-method compilation and ScriptValue execution exposed the Qt6
compatibility problems; their failed logs are retained with the final evidence.

No full native engine/header, custom converter corpus, thread-affinity policy,
manager-plus-VM resource teardown or informed-consent proof follows from this
fixture. Existing host Node22.23.1 tooling is not the locked native target.
