# Supported OAuth token responses

The AccountManager direct-import, login-completion and refresh-completion paths
now use the same production response validator. They accept the existing bounded
positive integral seconds lifetime and optional visible-ASCII refresh token,
with a nonempty Bearer credential and case-insensitive Bearer token type. Access
credentials permit letters, digits, `-._~+/` and trailing `=` padding. Whitespace,
controls, non-ASCII, embedded padding, padding-only values and unsupported token
types reject before account replacement, persistence, profile work or success.
No invalid credential is included in a diagnostic. Refresh tokens retain their
separate form-encoded syntax; they are not reinterpreted as Bearer credentials.

OAuthAccessToken's real JSON constructor applies the same validator, normalizes
the accepted type and converts already-bounded integer seconds in 64-bit
arithmetic. Its actual header-use boundary rejects malformed/unsupported or
expired restored values too. The stream layout is unchanged. The existing
explicit raw-token API's `expiryTimestamp == -1` sentinel remains supported,
including its empty type field; JSON responses cannot select that sentinel.
This does not establish server-side expiry or revoke an explicit static token.

The original complete AccountManager login/refresh and direct-import methods
are compiled in the existing Qt fixtures. New unsupported-type and credential
cases failed on the baseline. Existing status/type/size/expiry, duplicate/stale,
reentrant persistence and Application success-gating assertions are retained.
The accepted-token assertion compares against the input credential so the new
valid alphabet/padding case checks exact value preservation. A separate test
compiles the complete production OAuthAccessToken header, source, moc and stream
operators; it tests valid arithmetic, malformed responses, restored values and
raw-token compatibility. These are host tests, not platform/native login proof.

DomainAccountManager uses a separate domain-server packet protocol and is not
silently changed by this Bearer-header validation. Domain expiry/refresh, initial
origin/HTTPS policy, total framework allocation, native persistence/foreground
and complete token lifecycle acceptance remain separate open requirements.
