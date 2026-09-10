# Domain token lifetime

DomainAccountManager accepts a supplied `expires_in` only as positive integral
seconds within signed 32-bit range. Null, bool, string, fractional, zero, negative
and oversized values reject the response through the existing terminal failure
path. Accepted seconds become a precise monotonic QDeadlineTimer using 64-bit
milliseconds. The timer is copied with the domain's in-memory auth record; a
domain switch and later cache restoration cannot extend the lifetime.

`accessTokenIsExpired` is implemented, `hasValidAccessToken` checks the deadline,
and the actual `getAccessToken` getter returns no expired value. This getter is
the NodeList domain-auth packet consumer, so checking only the login-state API
would be insufficient. The actual NodeList packet block snapshots the admitted
token once; a second getter crossing the deadline can no longer serialize an
empty access credential with a refresh token. Its original source block is
compiled with a changing getter seam and real QDataStream; both admission and
exact packet bytes are asserted. Validity is checked when taking the snapshot,
not against future packet-delivery time. No already-sent packet is recalled by a
getter check, and cross-thread account mutation is not proven safe here.

Responses without `expires_in` preserve the existing session-only behavior;
they are not claimed to have server-verified expiry. Nothing is newly persisted.
Automatic refresh and server-side revocation are not implemented by this change.
The existing challenge path still requests explicit login. UI timer notification,
initial origin/HTTPS and full native/thread/foreground behavior remain open.

The original complete DomainAccountManager source, header and Qt moc are tested
with real Qt reply delivery and explicit transport/NodeList substitutes. Existing
request generation, cancellation, redirect, size, reentrancy, redaction and real
15-second deadline cases remain. New cases reject invalid expiry, accept one
second, wait for the real deadline, restore cached auth and require both logged-
out state and an empty public token getter. An absent-lifetime response preserves
the existing supported session behavior. The baseline rejected none of the new
invalid lifetimes; its new expiry mode failed. This is host evidence, not a real
domain server, platform clock/suspend or artifact acceptance result.
