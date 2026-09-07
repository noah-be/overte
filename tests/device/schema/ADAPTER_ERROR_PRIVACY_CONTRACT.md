# Canonical adapter exception privacy

The actual tests/device/run.py adapter_call used for discover, describe and
cleanup now discards adapter stderr at the child-process boundary. Nonzero
exit, startup failure, timeout, invalid text decoding and invalid JSON raise
only OVT_TEST_INFRASTRUCTURE_ERROR. Command/selector/path/native error text is
not copied into the exception and ordinary traceback chaining is suppressed.
Successful JSON is returned unchanged for the existing validators; this is not
a new adapter schema or an installed-artifact verification shortcut.

Requires sh004-results/v003 (and its result-identity/JUnit prerequisites). Import
run.py's narrow patch, not an incompatible full platform runner. No platform
adapter changes are required. This replaces free-form failure diagnostics with
a fixed infrastructure outcome; failures, target cleanup, identity pre/post
checks and original summary/JUnit status semantics remain in force.

Five focused tests call the actual function and real temporary child processes
for encoded/split/unlisted stderr payloads, nonzero exit, private argv timeout,
missing executable, malformed JSON, invalid UTF8 and successful protocol JSON.
No devices, builds, installed applications or screenshots were exercised.

Boundary: successful JSON remains trusted only after its normal schema/native
identity validation. Stdout capture is still unbounded and may contain private
data in memory; exception object contexts can still be inspected by custom
debuggers, although they are suppressed in ordinary formatting. This does not
sanitize module.log, module-owned artifacts, describe JSON, screenshot pixels,
other subprocess calls, arbitrary traceback locals or crash/export collectors.
Those remain pending PX16/SH004 work; no full privacy/node acceptance.
