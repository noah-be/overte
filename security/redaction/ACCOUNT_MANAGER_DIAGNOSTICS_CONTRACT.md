# AccountManager direct Qt diagnostic boundary — PX-16

All53 active direct qCDebug/qCWarning/qCritical expressions now use the existing
closed Shared vocabulary:52 Redacted events and the already-existing AuthReady.
Severity and conditional control flow remain. No auth URL/session ID/request
body/token/JSON/provider response/key-upload endpoint is formatted or evaluated
as a log payload. The two old diagnostic-only readAll expressions no longer drain
reply bodies solely for logging; ordinary transport/callback parsing remains.
Commented legacy debug examples are inert, not executed or accepted sinks.

The focused test executes the53 actual expressions through real raw Qt logging,
with an explicit positive unsanitized canary probe. It also compiles/runs complete
original setSessionID/publicKeyUploadFailed/handleKeypairGenerationError bodies,
preserving same-ID no-op, exact session mutation and waiting-state cleanup.
Fake reply accessor counters prove no raw endpoint/error access in that failure
body. This is expression/three-method proof, not full AccountManager integration.

Requires the published SafeDiagnostics taxonomy; matching Main/Apple variants
preserve existing transport/platform source. Other callbacks/assertion diagnostics,
stored diagnostic data, native exports/screenshots/crashes and actual retained
artifact privacy still require review. AuthReady is a diagnostic event, not
validated-token, consent or node acceptance. No auth/refresh/provider rewrite.
