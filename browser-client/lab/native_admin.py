# SPDX-License-Identifier: Apache-2.0
"""Generate machine credentials in the native HTTP Basic verifier format."""
import hashlib
import secrets


def native_admin_credential():
    """Return a fresh 256-bit CSPRNG token and native-compatible verifier.

    DomainServer.cpp requires SHA-256 hex for its HTTP Basic verifier. This
    no-input API only hashes random machine credentials, never human passwords.
    """
    token = secrets.token_bytes(32).hex()
    return {"token": token, "nativeVerifier": hashlib.sha256(token.encode("ascii")).hexdigest()}
