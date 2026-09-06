# Actual credential UI predecessor sinks

LoginDialog::login, loginDomain and signup no longer log the supplied username.
Their three qDebug expressions emit the existing fixed Redacted event. Actual
username/password/email dispatch, callback names and the Phone-specific
phoneLoginState.beginRequest gating remain byte-for-byte unchanged.

Requires px16-redaction/v001 SafeDiagnostics.h and the existing PhoneLoginState.h
where the Phone variant uses it. No dependency on the new DomainAccountManager
generation implementation: this is its independently necessary predecessor
sink closure. Apply the narrow source patch, preserving all variant-specific
login gating/routes. Do not replace a different platform's whole LoginDialog.

The focused test compiles all three COMPLETE original bodies with real Qt JSON
and the original PhoneLoginState. It verifies both Phone and non-Phone paths,
one pending Phone dispatch, exact live credential values and signup payload/
callback delivery to explicit transport boundaries, and raw unsanitized Qt log
capture. AccountManager/DomainAccountManager network calls are substitutes here;
the separate domain-auth test exercises the actual credential manager.

Set OVERTE_LOGIN_VARIANT=main for Main/Phone/Pico, or apple for the retained
Apple implementation (Phone OR iOS pending-request guard). The same original
test covers all three define stacks with explicit expected guard ownership.
Raw Qt debug logging is explicitly enabled and positively probed before the
actual calls; an ambient disabled debug filter cannot produce a false pass.

No whole dialog/QML, native provider, TLS, consent or privacy/node acceptance.
Other constant LoginDialog diagnostics, other Shared sinks, in-memory values,
module logs and retained export/crash/screenshot privacy remain separate work.
