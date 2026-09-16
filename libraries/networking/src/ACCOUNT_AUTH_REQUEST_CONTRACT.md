# Account credential POST boundary — SH-005

The five actual AccountManager password/auth-code/Steam/Oculus/refresh request
methods now explicitly request ManualRedirectPolicy. Credential POSTs must not
automatically follow a server redirect, including to another HTTPS origin. The
completion v003 callbacks already reject non2xx responses; no browser or
automatic redirect fallback is introduced. Servers must expose the final token
endpoint directly. This does not validate the original configured origin/HTTPS
scheme or authorize any new provider/product route.

Auth-code client ID/secret/code and Oculus nonce/ID now use the same percent
encoding as existing password, redirect URI and refresh fields. Delimiters,
plus/percent/equals/control and Unicode data stay in their original field instead
of creating extra form parameters. Existing grant/scope, URL construction,
receiver wiring and no-refresh-token/no-POST behavior are retained.

All five COMPLETE original methods execute through actual QNetworkAccessManager
post/createRequest, inspecting the real request/form and emitting real finished
signals. The createRequest override returns a test reply instead of opening any
socket. Whole completion methods have their own v003 suite. This is request
construction/Qt-policy evidence, not a live TLS/redirect-server/provider test.
Main's original pre-Qt6 string error connections remain unchanged; Apple retains
its version guards. This fixture verifies finished receiver wiring, not those
legacy error connections, and does not claim they were repaired.

Requires matching Account completion v003 and diagnostic/storage chain plus the
existing original-method extractor. Export Main and Apple variants separately,
preserving Apple Qt guards. Deadline, streaming/total-memory limits, cancellation,
generation/foreground/retry/backoff, initial URL policy, binary Steam tickets,
setAccessTokens injection, provider availability and full native/artifact/privacy
acceptance remain pending. No frozen Cold Build inputs are modified.
