# Login pending ownership and observer lifetime

Domain pending state now comes directly from the actual DomainAccountManager's
owned QPointer reply through isAccessTokenRequestPending(). No second static
domain pending flag is created. Context cancellation clears that owner before
abort; the existing reply/ticket fence rejects stale finish, so old completions
cannot clear a new request. The actual manager test observes pending through
domain/auth/client changes, supersession and success. Its finite deadline and
response validation remain unchanged from domain-auth-generation/v003.

For Main Phone / retained Apple Phone-or-iOS guards, login() and loginDomain()
both reject another live account OR domain request. Only account login calls
PhoneLoginState::beginRequest. isPhoneLoginRequestPending() reads the union of
the account gate and real domain pending owner, including when a view is reopened.
Domain success/failure never clears an account's gate.

AccountLoginStateBinding observes actual AccountManager complete/failure and
destruction with an application-owned QObject, not a per-dialog receiver. A
reopened dialog reuses the same binding. Manager replacement destroys the old
observer before resetting/admitting a new gate; old-context queued signals and
destruction cannot clear that new gate. This retains the existing UI-thread
assumption; it is not a cross-thread synchronization retrofit. The original
AccountManager request-generation/target-change handling remains separate work.

The focused tests compile the COMPLETE original constructor, credential methods,
pending getter and binding header with real Qt signals/QML Connections. They
test closed-view completion/failure, manager replacement with a queued old
outcome, destruction, observer reuse, domain result not clearing account state,
actual domain admission blocking and post-cancellation re-admission. Credentials,
raw log canaries and all platform guard expectations remain checked. The actual
DomainAccountManager header/all-method fixture separately tests the real pending
getter, current/stale replies and 15-second deadline.

Requires domain-auth-generation/v003 plus its complete v001/v002/discovery
snapshot/redaction chain, matching login-dialog diagnostics and domain-login-
receiver/v001, existing PhoneLoginState and LoggingInBody.qml. Import the new
header and all listed modified files together. Apple has a separately prepared
delta preserving every Phone OR iOS guard; never substitute Main whole source.

This closes pending admission/lifetime state, NOT complete cancellation UX:
an already visible spinner still needs generation-bound cancellation/error
delivery and typed timeout presentation. No blind loginFailed-on-cancel is
added, because it could address a newer view. Native Qt5/thread/foreground,
provider, cross-dialog presentation identity and full artifact/node evidence
remain pending. No platform-owned caller or frozen build input is modified.
