# PX-16 DomainHandler closed diagnostics v001

All 30 direct Qt log expressions in the actual DomainHandler now emit only
`diagnosticEvent(DiagnosticEvent::Redacted)`. No hostname, socket, domain UUID,
server settings, denial reason/extraInfo, counter or queue payload enters those
calls. The inadequate URL-prefix filter and diagnostic-only queue inspection
are removed. Severity and category remain unchanged. This deliberately reduces
diagnostic detail; no domain/product behavior or user-facing data is sanitized.

Requires px16-redaction/v001 SafeDiagnostics.h (source
6f11d1bedf620b39a0c05d93e27fed64b85b1208, manifest
203f5a8498989f40f5f2760282960ed78b16b62d4e624d618de601a34688c52b).
Import after sh005-ice-hostname/v001 source5177f6c24d47f1cbcddc7fd0265c4eb687f06315,
manifest5c10a279c23e42ae96904eb27126f086c95d324eee8ea28b63c957418961a814:
the delta preserves its cancellation and adjusts only its focused test include.

`test_domain_diagnostics.py` compiles every actual payload and both complete
production settings-receipt/error-redirect methods with real Qt and a raw capture
sink without global sanitization. Canary settings, reason, extraInfo and URL
remain intact in legitimate signal receivers while diagnostics stay closed.
Packet/signal receivers and unchanged policy predicates are test boundaries.
The actual ICE setter/completion regression remains green after this change.

Pending: full DomainHandler/platform compilation, other network/third-party
loggers and OS sinks, physical canary privacy/evidence tests and original PX-16
acceptance. This is a local implementation release, not whole-client privacy PASS.
