# Domain credential reply ownership

The actual DomainAccountManager now owns one pending credential reply and uses
the existing RequestScope/RequestTicket contract. Changing domain URL, auth URL,
client ID, starting a new credential request or destruction invalidates the old
ticket and clears pending ownership BEFORE abort can synchronously emit finished.
Replies are scheduled for deletion on finish or cancellation. The terminal slot
requires the exact owned QNetworkReply and its current ticket, clears ownership
once, then retains the existing success/error handling. Direct calls with no
sender and duplicate/stale/foreign replies cannot install tokens or emit success.

The real 500ms authRequired dialog callback captures that same scope's snapshot;
a context change or newer login request suppresses the old dialog. Requests with
an exhausted scope fail closed. Same-value setters remain no-ops. Domain/account
state and successful token/refresh-token signals remain otherwise unchanged.

All five DomainAccountManager diagnostic expressions now use existing closed
events, including OAuth server error/description and private domain/auth URLs.
The real original diagnostics sink is captured in the focused test; credential
values still travel to the legitimate HTTP/token/UI consumers, not the logger.

Prerequisites: RequestCancellation.h from sh005-http-cancellation/v001 with its
v002 correction, and px16-redaction/v001. Import both production files and both
new test files plus this document. No new platform/native API; setClientID moves
from inline to the same actual implementation. Preserve platform-specific source
on any contextual conflict; report it instead of transplanting a whole variant.

The test compiles ALL original DomainAccountManager methods and its original
Q_OBJECT header with real Qt moc, timers, JSON, QNetworkAccessManager post and
QNetworkReply signals. Only dependency/NodeList and actual network transport are
substituted; no real connection is made. It covers each supersession, success,
duplicate/no-sender, HTTP/malformed failure, delayed dialog, destruction and
raw diagnostic canaries. This is not a whole networking library or device build.

Pending: actual native Qt5/thread-affinity execution and end-to-end domain login,
global foreground/lifecycle fence, finite request timeout/recovery UI, TLS and
redirect/origin credential policy, strict token response types/expiry/refresh,
cached-domain authorization policy and other auth requests. Existing cross-thread
ownership assumptions are not made safe by the atomic ticket alone. The former
in-flight state mix-up is closed in this caller; no full SH005/PX15/PX16 PASS or
installed artifact claim follows. The frozen SH001 build source is unchanged.
