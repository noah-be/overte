# Address lookup continuation identity

Actual API success/error handling retains the lookup snapshot and a guarded
reply throughout processing. The address response handler rechecks after direct
network/ICE domain-change and host-change notifications before writing later
state, selecting a path or reporting completion. It rejects a deleted reply.
Host/domain setters and history insertion retain the same request snapshot and
stop after reentrant history/host notifications. History records the address
captured before notification rather than a later replacement target.

The focused fixture compiles six complete production functions: API response,
address-object processing, API error, host setter, domain setter and history.
It uses actual RequestCancellation.h, Qt signal dispatch, QPointer, QNetworkReply
JSON reads and Qt history/URL containers. NodeList connection timing/domain-error
queries and final path/viewpoint delivery are explicit seams. Cases cover direct
and ICE replacement, reply deletion during a direct signal, host replacement,
not-found replacement, host/domain history reentrancy, domain signal suppression,
normal successful history/path/completion and stale reply rejection. Removing
actual lookup-current comparisons fails the first replacement assertion. The
existing redaction fixture still checks all original19 sink expressions and
404/stale behavior; its harness now supplies the production RequestScope.

Already emitted notifications are not rolled back. This does not prove all
handleUrl entry/history cases, cross-thread AddressManager ownership, finite
network abort or native/platform lifecycle acceptance. No informed entity-script
allow path is enabled. Private endpoint logging remains redacted.
