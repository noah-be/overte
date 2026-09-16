# Domain token session-cache context invalidation

Changing the actual OAuth client ID now clears access/refresh tokens and the
authenticated-domain display name. Changing the auth URL also clears that name.
Both changes remove the current domain's saved session entry. Starting a new
credential request removes the prior token/name/cache entry before testing request
admission, so failure cannot revive the previous credentials after navigating
away and back. Same-value client/auth updates remain no-ops; unchanged context
still restores its valid session entry on returning to the domain.

This is an in-memory scope fix, not a new persistent credential store or an
approved origin/HTTPS/expiry/refresh policy. Old tokens are not sent to a new
client context, and an explicitly replaced session is not silently restored.
Request generation/outcome/deadline/transport and existing signal signatures are
unchanged. Other-domain cache entries remain intact.

The existing full original DomainAccountManager/header/moc Qt fixture now creates
real session entries and exercises all three invalidation paths, unchanged-context
reuse and leave/return negatives. Original stale/abort/form/redirect/size/outcome
and real15-second deadline tests remain. Transport is the existing fake reply;
no provider/Qt5/native/thread or artifact acceptance is inferred. Prerequisite:
domain-auth-generation/v003 plus domain-login-outcome/v001 and their full chain.
Global foreground, reentrant context setters, account-manager binding, token
expiry/refresh validation, private cache capacity and full acceptance remain open.
