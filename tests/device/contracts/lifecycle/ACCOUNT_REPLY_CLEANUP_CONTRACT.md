# Account reply cleanup after reentrant request creation

Requires matching account-profile-context/v001, account-login-order/v001 and
their full transitive prerequisites. This is an additive source correction, not
a replacement for those contracts or a native/platform acceptance claim.

The four interactive POST methods, refresh POST and profile GET may regain
control after the network boundary has replaced their context or destroyed the
AccountManager. These early-return paths have no finished receiver. They must
schedule the returned reply for deferred deletion, without connecting stale
account callbacks or clearing a newer request's pending state.

The original complete production methods are compiled with real Qt replies,
tickets and moc; transport and account persistence remain explicit test seams.
The auth fixture checks all four providers and refresh at user-agent/POST
replacement and destruction boundaries. The profile fixture checks credential
invalidation, a newer profile request and manager destruction inside GET.
Deferred-delete drains prove reply cleanup, and the replacement requests retain
their normal success/persistence behavior.

Both new cleanup assertions fail on Main a8efb31a07 before the fix (auth3.028s,
profile2.120s); fixed Main passes auth2.846s and profile2.189s. This does not prove
native network behavior, concurrent threads, total streaming bounds, foreground
recovery or original full-node acceptance. Preserve Apple error-slot connections.
