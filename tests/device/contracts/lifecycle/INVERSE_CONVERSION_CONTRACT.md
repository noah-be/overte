# SH005 inverse conversion and signal admission

The complete production `ScriptEngineV8::castVariantToValue` now rejects work
when the permanent abort latch is set. It rechecks before and after registered
native marshal callbacks, so a callback that stops its engine cannot hand a
value back into later unwrapping. This does not interrupt an already-entered
native callback or prove its duration.

Custom prototypes are copied under a scoped Qt read lock and passed to proxy
creation after unlocking. The former successful-lookup return retained the
read lock permanently. The snapshot remains alive through proxy creation even
if a reentrant registry update removes the registered entry.

The actual Qt signal meta-call checks admission before each argument and after
conversion. A converter that stops and clears V8's transient termination state
still prevents later argument conversion and callback delivery.

`test_v8_inverse_conversion.py` compiles the complete production inverse method
with actual QVariant/QHash/QReadWriteLock and host V8. Six runtime cases cover
ordinary scalar/null/string values, a custom converter, prototype creation with
a reentrant registry removal, two stopped entries, and a converter-triggered
stop. Wrapper storage/unwrapping and QObject/variant proxy creation are explicit
seams; prototype creation asserts that the real registry write lock can be taken.
`test_v8_signal.py` executes the complete production meta-call with real moc
signals and V8 callbacks; its conversion seam can stop during the first of ten
arguments. The previous-source controls compile unchanged previous method bodies
and fail the corresponding lock/admission assertions.

This is focused host evidence, using the existing Node 22.23.1 V8 fixture tools,
not the source-locked native target. Full engine/proxy headers, custom demarshal,
combined native manager/VM teardown, all native converter implementations and
informed consent remain unaccepted. No consent grant is enabled.
