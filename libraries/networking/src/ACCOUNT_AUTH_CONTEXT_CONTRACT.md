# Account credential context fence — SH-005

The existing RequestScope/RequestTicket/watchRequest contract now binds all five
credential POST paths to one AccountManager-owned context. Logout and a changed
auth URL advance it BEFORE replacing account state; the same URL remains a no-op.
Returning A→B→A does not revive A's old ticket. Scope destruction invalidates
outstanding tickets. No competing token/schema or URL identifier is introduced.
The context snapshot is captured BEFORE post(), so a context change reentered
from Qt's request-creation seam cannot bless the old request with a new ticket.

Both finished callbacks discard stale replies after arranging cleanup, before
parsing, login signals, credential assignment, persistence or profile requests.
Refresh rejects stale error callbacks before changing the waiting flag; context
transitions clear that flag for the old context. Original watchRequest observes
invalidation in the reply thread on its20ms timer; this is not a hard OS abort
guarantee. An abort emitting a success-looking finished signal remains stale.

Actual logout/setAuthURL/password/refresh/completion/error methods execute with
the original RequestScope and real Qt POST/replies. Tests cover logout, changed
URL, A→B→A, same-URL no-op, a fresh admitted login, and old refresh completion/
error while a newer refresh waits, and logout reentered during the actual POST
seam (an initially post-captured draft fails this negative). The five-request test verifies actual ticket
metadata. Storage/profile/stored-account load and complete AccountManager setup
are explicit fixture boundaries, not accepted native integration.

Requires matching Account deadline v001, request v001, completion v003, original
RequestCancellation.h (domain-outcome/snapshot prerequisite chain), diagnostics
and protected-account prerequisites. This fences context, NOT latest-request
ordering within the SAME context; concurrent login/refresh policy still remains.
Calls retain existing object-thread assumptions. Separate Apple's login error
callback may still emit failure for stale replies; discarded old completions do
not establish complete UI cancellation recovery. Foreground, initial URL policy,
streaming memory, reentrant callbacks, full native/artifact evidence remain open.
