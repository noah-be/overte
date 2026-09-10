# Domain credential visibility binding — SH-005

The real Application Qt/native visibility publisher now sends its existing
effective foreground decision to DomainAccountManager as well as AddressManager
and NodeList. No second native observer, visibility combination or schema exists.
The existing startup observation runs after DomainAccountManager installation;
early native callbacks retain their inputs without constructing dependencies.

DomainAccountManager::setClientAuthVisibility marshals to its QObject thread.
Loss captures the ORIGINAL request ticket, deactivates the request scope BEFORE
abort, clears the actual pending owner and emits the existing request-bound
Cancelled outcome. Capturing after setActive would lose the UI's ticket identity;
the implementation and actual manager test explicitly retain it. Duplicate loss
does not replay credentials or resurrect tokens. Late success is ignored and
background new requests emit failure without a POST. Old delayed prompt tickets
also become inactive. Resume activates future explicit requests, never automatic
credential replay; prior tickets remain invalid. Existing completed session tokens
are not a new sign-in and are not logged out merely by backgrounding.

Actual full publisher tests cover both visibility-source orders, early startup,
native queued handoff and stopped state using explicit dependency boundaries.
Actual complete DomainAccountManager/header/moc tests cover original ticket
cancellation, synchronous abort-success race, late result, background admission,
no-auto-resume and a real std::thread-to-QObject queued pause. Existing form,
response/cache/outcome/deadline tests remain, including real15s timeout. No test
shortens that timer. Baseline publisher fails at its missing domain observation.

Requires visibility-inputs/v001, discovery/transport visibility prerequisites,
domain-auth-cache-context/v001, domain-login-outcome/v001 and entire original
helper chain. Import matching Main/Apple variants because Application_Events has
platform differences. No platform-owned native caller changes are included.

This is not a hard OS-stop guarantee: cross-thread notifications need event-loop
delivery, and blocked native/TLS operations are not proved. Generic AccountManager
auth, consent, full foreground recovery, expiry/refresh/origin policies, reentrant
setters, native Qt5/Qt6 integration and accepted artifact/device evidence remain.
