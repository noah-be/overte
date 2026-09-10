# SH-005 DomainHandler ICE hostname ownership v001

The actual `setIceServerHostnameAndID` no longer placement-destroys/reconstructs
its SockAddr QObject to launch unowned DNS. Numeric addresses use the existing
immediate completion path. Names use a separate `ScopedHostnameLookup` owned by
DomainHandler. `hardReset` cancels both direct and ICE DNS before `resetting`
or socket/domain mutation. Only a current once-consumed successful IPv4 lookup
sets the ICE socket and reaches the existing completion/heartbeat signal.
Failed/empty/IPv6-only DNS replies do not publish an ICE completion, preserving
the original async SockAddr IPv4 selection policy. Numeric IPv6 behavior is
unchanged. No new platform hook or connection schema is introduced.

Prerequisite: sh005-scoped-hostname/v001 source
a0a067f05fcf35acdb9777c657fa2b7649bd96ae, manifest
f61a07a814241f4b575e73aeecccb7d647a2098288c14c0d757dd4acbf5546af,
including its RequestCancellation dependency. Both lookup owners stay in the
DomainHandler event-loop thread. Qt abort remains best effort, not a hard
OS-stop deadline. General SockAddr callers are not modified by this delta.

Focused checks: `test_ice_hostname.py` compiles the complete original ICE setter
and completion and the actual pre-reset cancellation prefix with real Qt,
original RequestScope and ScopedHostnameLookup. The OS resolver, SockAddr value
storage, NodeList timing receiver, signal receiver and unchanged reset tail are
explicit test boundaries. Reused IDs/reentrant abort, domain switch, reset,
numeric fast path, duplicate/stale delivery, errors, IPv6-only/empty answers,
failed launch, recovery and destroyed owner pass. The existing two direct-DNS
checks also pass, including actual isolated Qt numeric asynchronous resolution.

Pending: full DomainHandler/Qt5/platform compilation; foreground suspension and
restart of discovery, other SockAddr/STUN/ICE response and transport queue
ownership, bounded reconnect/deadline/recovery UI, closed DomainHandler raw
diagnostics, consent/finite revoke and original artifact/device acceptance.
This source contract is not full DNS/transport cancellation or SH-005 PASS.
