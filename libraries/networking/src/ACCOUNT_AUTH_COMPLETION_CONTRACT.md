# Account credential finished-response boundary — SH-005 v002

Additive v002 requires nonempty string access_token/token_type, numeric whole
expires_in in [1, 2147483647] seconds, and a string refresh_token if present.
The optional refresh token may be absent or empty. The integer bound is the
signed-32-bit seconds representation accepted by QJsonValue::toInt, not a
recommended credential lifetime or server-expiry policy. It prevents malformed
types and enormous/fractional lifetimes reaching OAuthAccessToken's unchecked
double-seconds conversion. Invalid responses emit the existing failure outcome
without replacing/persisting the previous account or requesting a profile.
String token grammar, supported token-type semantics and refresh callback
validation are NOT established by these checks.

The actual requestAccessTokenFinished callback now emits loginFailed for its
existing missing-field case instead of only logging and leaving UI pending.
It rejects network errors, non2xx status, malformed/non-object JSON and final
response bytes beyond1MiB; its read is capped at1MiB+1. It validates the sender
type, consumes each reply's finished path once and schedules reply deletion on
every outcome. Existing success token assignment/loginComplete/persist/profile
order is preserved; rejection does not overwrite an existing account record.

The complete actual callback executes on real Qt QNetworkReply::finished/moc
with malformed/missing/status/network/size/exact-limit/duplicate/no-sender/deferred
deletion cases. Persistence/profile/account-data objects are explicit boundaries;
no real protected-store/provider/full AccountManager evidence is inferred.
Baseline fails at the original missing-field path's absent terminal signal.

Requires matching AccountManager diagnostic release, original SafeDiagnostics and
the existing block extractor test_login_dialog_domain_receiver.py. Separate Apple
export preserves its extra error callback and Qt6 guards. Its errorOccurred path
may independently signal loginFailed; per-finished de-duplication is NOT a claim
of exactly-once outcomes across all signals. Other live reply buffering/TLS/JSON
allocation, token grammar/server expiry/refresh callback validity, redirects, target generation,
foreground/consent, complete UI/privacy and artifact/native acceptance remain.
