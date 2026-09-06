# SH-005 direct-domain DNS generation cancellation

IMPLEMENTATION ONLY. Requires sh005-http-cancellation/v001's original
RequestCancellation.h (and v002 when importing that release's startup caller).
This slice binds the real DomainHandler resolver beneath the Shared
AddressManager/NodeList connection path. The narrow DomainHandler source touch
is necessary because that is where QHostInfo is actually launched and delivered;
there is no platform override, parallel network schema or new native hook.

The direct-domain QHostInfo request is owned by ScopedHostnameLookup. Each
start invalidates the previous generation before calling Qt abortHostLookup.
DomainHandler hardReset cancels before emitting resetting or mutating the
domain/socket. The original socket-setting callback is reached only by a
current, once-consumed generation. Resolver IDs and hostname equality are NOT
used as freshness evidence. Destructor/receiver destruction/failed launch and
queued or duplicate old completions fail closed. Completed IDs are cleared
before calling consumer code; receiver-destroy connections are disconnected.
Objects are used in the receiver's event-loop thread, as the original caller.

QHostInfo abort is best effort, not evidence that OS resolver work stopped within
a physical deadline. No external resolver payload or URL is added to evidence.
Existing raw DomainHandler diagnostics are not rewritten by this slice.

Focused check: tests/device/contracts/lifecycle/test_scoped_hostname.py compiles
the original helper and original DomainHandler launch expression with real Qt6
objects, plus deterministic OS-resolver-only substitution. Tests include
reentrant delivery during abort, deliberately reused IDs, stale domain/duplicate
callbacks, lookup owner/receiver destruction, wrong receiver thread, invalid
input, failed launch, and a positive Qt asynchronous numeric-loopback lookup.
Both executables run in isolated network namespaces. This is NOT a compiled
full DomainHandler or a simulated domain connection; the socket consumer is a
test boundary. Full Qt5/Qt6 client compilation remains pending.

Still pending: foreground suspension of all DomainHandler/NodeList work; ICE
SockAddr resolver ownership; UDP/check-ins, STUN and reconnect cancellation;
bounded connection/recovery UI/typed trace and entity-script informed consent
with finite revoke. This contract must not be relabeled as SH-005 PASS, complete
DNS lifecycle coverage, full connection cancellation or device acceptance.
