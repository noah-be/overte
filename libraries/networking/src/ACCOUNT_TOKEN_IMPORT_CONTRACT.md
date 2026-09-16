# Direct Account token import and Application caller

PX-15 / SH-005, cohort #685. Prerequisite corresponding account-auth-context/v001
and protected-store/redaction chain. Main context fa3abe7fd0ac329f0f3392b4237eb0cf3e196ad3;
Apple context f236051044833b1186a192ee0fc978538acb6358. Existing reentrancy variants
remain compatible; this release specifically covers the separate direct caller.

`AccountManager::setAccessTokens(const QString&)` now returns bool. Import its
header, complete implementation AND the real `Application::forceLoginWithTokens`
caller together. True means the direct token response was accepted and its
credential context/owner stayed current through the existing synchronous actions;
it is NOT proof that a native credential store successfully persisted data.
Existing void persistence/save/profile APIs and their error policies are unchanged.
The Application caller sets KEEP_ME_LOGGED_IN only on true. Invalid input does
not write that setting or reset a pre-existing user setting implicitly.

The input has an inclusive1MiB UTF8 limit; UTF16 length is checked before
conversion, then UTF8 length before parsing. Malformed/non-object JSON, explicit
error, absent/empty/non-string access token or token type, nonnumeric/fractional/
nonpositive/out-of-int32 expires_in and non-string optional refresh token emit
loginFailed and return false before modifying account/persistence/profile state.
Empty optional refresh tokens are supported. Limits constrain this parser, not
the memory allocated by the producer of the already supplied QString.

With account-persistence-context/v002, successful login assigns tokens, invokes
protected persistence, emits loginComplete, invokes saveLoginStatus and
requestProfile in that order. A reported store failure invalidates the context
and requests re-auth before any loginComplete. Original RequestScope ticket
and QPointer guard between every reentrant boundary stop subsequent work after
context invalidation or destruction. The final guard also stops the Application
preference write if profile startup invalidates/destroys the manager. Already
entered storage/profile actions are not undone by this check.

Focused test compiles the complete ORIGINAL setAccessTokens and Application
caller using their actual declared return type, real Qt signals and explicit
storage/profile/settings boundaries. It covers malformed and field/type inputs,
inclusive byte limit and multibyte overflow, positive max expiry, exact accepted
actions, and context invalidation/destruction at four successive callback seams.
Old source fails on its silent malformed-response path. Neither source methods
nor their return type are rewritten inside the fixture.

Pending: incoming token authenticity, optional response URL/origin/HTTPS policy,
token grammar/server expiry/refresh semantics, same-context request ordering,
native protected-store result propagation, full UI/foreground and actual
native/provider/artifact/node acceptance. No new provider/auth origin is approved.
The frozen cold build proves only its own earlier SHA, not this source update.
