# SH-005 NodeList foreground entry fence

Requires sh005-visibility-inputs/v001's real effective Qt/native publication.
The same out-of-line Application publication now forwards its effective value
to NodeList when installed, without early dependency construction. Setup seeds
visibility immediately after installing BOTH AddressManager and NodeList.

Atomic, C++-only setClientTransportVisibility(bool) prevents starting six actual
NodeList paths while suspended: domain check-in, ICE server query, domain ping
punch, inactive-node ping punch, node-hole-punch start, and keep-alive pings.
No timers, connection counters, source addresses or packet payloads are rewritten.
Unmanaged assignment/server processes retain their original behavior; a mutable
owner type does not enable/disable this full-client policy. Duplicate pause is
idempotent. Foreground permits existing paths again, but does not itself call
them. A stopped application Gate continues publishing false.

This is an ENTRY fence, not cancellation of a send already past its guard. A
cross-thread Qt/native event becomes effective when its existing GUI-thread
publication runs; no synchronous native stop/deadline is claimed. Old timers may
run again after foreground. Full generation-bound reconnect/retry/deadline/UI,
stale reply handling, DomainHandler discovery, LimitedNodeList STUN, transport
queues and actual in-flight socket cancellation remain pending. Do not label
this complete background network isolation or SH-005 PASS.

Pico's narrowly released startup change: move the existing
overte::lifecycle::observeQtVisibility(QGuiApplication::applicationState() == Qt::ApplicationActive)
line from after AddressManager to immediately after DependencyManager::set<NodeList>.
Keep one seed, same include, later activeChanged/native bindings unchanged.
Phone/iOS use the actual Shared startup file; no new native callback signature.

Tests compile the actual atomic setter/state, five original entry fragments,
and the COMPLETE original keep-alive method (with explicit packet/node boundary
substitutes). Existing full publication test uses real Qt queued calls plus
AddressManager/NodeList receiver boundaries and checks early callbacks, both
visibility orders, duplicates, thread queue, and stopped-Gate veto. These are
focused host tests, not a complete NodeList/Qt5/native/socket timing proof.
