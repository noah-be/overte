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

Version 002 adds a real single-shot 15s Qt deadline parented to each reply. A
current timeout invalidates ownership before abort, then emits loginFailed
exactly once through the existing UI signal. Finished replies stop the deadline;
stale/dead manager callbacks cannot run through the QObject context connection.
No automatic retry is added. A dedicated test waits for the actual production
15s timer, including abort's synchronous apparent-success signal and reply
deletion. This is an event-loop deadline, not a hard OS stop guarantee while
the thread is blocked or the application is suspended.

All five DomainAccountManager diagnostic expressions now use existing closed
events, including OAuth server error/description and private domain/auth URLs.
The real original diagnostics sink is captured in the focused test; credential
values still travel to the legitimate HTTP/token/UI consumers, not the logger.

Prerequisites: RequestCancellation.h with snapshot() from
sh005-discovery-visibility/v001 source6026087a7942c224ac0086ece436cb61f5302ac1,
manifest83c72c242b095114af7db65739faa3b793fe668d0850483f50a62cad63575b8b,
helper SHA2564e348bbe82e4e5c3be0705e0bb73f80bf880fd0b4e3023ea71465142df8acdce,
and px16-redaction/v001. This incorporates the mandatory additive v001/v002
prerequisite notice; older sealed exports remain unchanged. Import both production files and both
new test files plus this document. No new platform/native API; setClientID moves
from inline to the same actual implementation. Preserve platform-specific source
on any contextual conflict; report it instead of transplanting a whole variant.

The test compiles ALL original DomainAccountManager methods and its original
Q_OBJECT header with real Qt moc, timers, JSON, QNetworkAccessManager post and
QNetworkReply signals. Only dependency/NodeList and actual network transport are
substituted; no real connection is made. It covers each supersession, success,
duplicate/no-sender, HTTP/malformed failure, delayed dialog, destruction and
raw diagnostic canaries. This is not a whole networking library or device build.

Version 003 percent-encodes client_id as well as username/password, so a supplied
client ID cannot add form parameters. Credential POST requests explicitly use
ManualRedirectPolicy; 3xx is failure, never automatic credential replay. The
reply read buffer is set to 1 MiB plus one byte, readyRead rejects oversized
current responses with invalidation-before-abort, and final read/JSON input is
bounded to that sentinel limit. Exactly 1 MiB is accepted if otherwise valid.
Only error-free 2xx, valid JSON objects with a nonblank string access_token and
an absent or string refresh_token can install tokens/emit success. Empty optional
refresh tokens remain supported. A network error with a 200/token payload is
not success. Failure uses existing loginFailed, with no payload logging.

The original-method/header test adds form delimiters/Unicode, actual request
redirect/buffer settings, 3xx, malformed/top-level/type/empty/blank token cases,
optional-refresh types, network-error-with-200, finished/streaming oversize,
duplicate finish/readyRead and inclusive-size success. The original real15s
timer and all generation tests are retained. This is a public Qt reply/input
bound, not a proof of total Qt/TLS/decompression or JSON allocation memory.

Pending: actual native Qt5/thread-affinity execution and end-to-end domain login,
global foreground/lifecycle fence, blocked-thread/OS timeout and recovery UI, TLS and
initial auth origin approval/TLS policy, token syntax/expiry/refresh semantics,
cached-domain authorization policy and other auth requests. Existing cross-thread
ownership assumptions are not made safe by the atomic ticket alone. The former
in-flight state mix-up is closed in this caller; no full SH005/PX15/PX16 PASS or
installed artifact claim follows. The frozen SH001 build source is unchanged.
