# Account value diagnostics and signature result

DataServerAccountInfo::setUsername and getUsernameSignature now emit fixed
technical messages. The username and connection UUID remain inputs to the
actual signature; they are not copied into diagnostics. The other diagnostics
in this class already contain fixed text. Profile field updates and serialized
fields retain their existing behavior.

RSA_sign success is exactly 1. On success the returned QByteArray is resized to
the reported signature length. Failure returns an empty result, so the caller
cannot mistake an allocated zero-filled buffer for a signature.

The focused fixture compiles the complete production DataServerAccountInfo.cpp,
complete OAuthAccessToken.cpp, original headers/moc and local Qt/OpenSSL. It
executes profile updates, generates an ephemeral host unit-test key, verifies the
actual username/UUID signature, checks invalid/missing-key behavior, and captures
direct Qt logging without relying on the application's final sanitizer. The sole
crypto seam can force RSA_sign to return failure; normal calls reach OpenSSL.
Reinstating the old private diagnostic expressions fails canary assertions.
Reinstating the whole old signature-result block (condition and untrimmed buffer)
fails the forced-failure assertion. Changing only the condition does not fail
because the new length handling independently empties that result.

No product key, signing identity, platform keystore, release signing or native
application build is used. This is not a complete network authentication test,
RSA API modernization, side-channel analysis, whole-application privacy or PX-17
artifact-bound vulnerability disposition. Original39 acceptance remains open.
