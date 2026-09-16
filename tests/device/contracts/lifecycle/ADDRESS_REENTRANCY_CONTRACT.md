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

The outer entry batch adds complete production handleUrl, handleNetworkAddress
and handleUsername to the same fixture (OVERTE_ADDRESS_INCLUDE_ENTRY=1).
Recognized but superseded requests stop their remaining effects while retaining
handled=true, avoiding an unhandled-URL fallback. File/HTTP and relative-path
completion notifications are followed/preceded by request checks as appropriate.
IP/DNS helpers stop after a superseding early completion; username history intent
is stored before starting its HTTP lookup, so a synchronous callback cannot be
overwritten on return. Original event ordering is retained when no new lookup
supersedes the request; already emitted notifications still cannot be rolled back.

Cases cover normal HTTP/file/relative/IP/DNS/user/domain-ID/place routes, direct
host/completion/path reentrancy, user-request reentrancy, logger reentrancy and
foreground/explicit-intent gating. Removing guards only from the three new
entry functions fails the outer HTTP path assertion while the six earlier
functions retain their guards. NodeList, final path/viewpoint and HTTP dispatch
are explicit seams; the latter advances the actual RequestScope and can reenter.
The unchanged Main QRegExp expressions use a named Qt6 test adapter in this host
fixture; Apple runs its actual QRegularExpression implementation. Neither this
adapter nor these route cases prove native Qt5 parser equivalence, complete URL
security policy, all deep path/history callbacks or cross-thread ownership.

The viewpoint batch includes complete actual handlePath and handleViewpoint
(OVERTE_ADDRESS_INCLUDE_VIEWPOINT=1), for eleven production functions total.
Float conversion success and finite positions are checked before history or
movement. Recognized invalid coordinates are consumed without named-path fallback.
Orientation starts as explicit identity; invalid/zero/overflowing components keep
orientationChanged=false while the valid position remains usable. Double length
intermediates normalize the complete finite float range without float-square
underflow/overflow. PAL yaw adjustment runs only for a valid supplied orientation.
History and named-path continuations recheck the lookup snapshot.

Cases include each overflowing position coordinate, absent/zero/overflowing
orientation, ordinary/large/small normalized orientation, inactive named paths
and a superseding history notification before movement. Removing the position
validation fails the invalid-coordinate assertion. The fixture's GLM boundary is
value-only vec3/quat constructors and a counted PAL-yaw seam: all conversion and
normalization arithmetic comes from production. Host GLM headers are unavailable;
this does not prove native GLM ABI, configured default-constructor behavior, PAL
rotation math, physical world-coordinate limits or complete native URL parsing.
