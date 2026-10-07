// SPDX-License-Identifier: Apache-2.0
import { randomBytes, createHash } from 'node:crypto';

// Native DomainServer HTTP Basic requires SHA-256 hex (DomainServer.cpp).
// This is exclusively a verifier for a fresh 256-bit machine credential.
// It cannot receive a human password or caller-supplied low-entropy secret.
export function nativeAdminCredential() {
    if (arguments.length !== 0) throw new TypeError('Native administration credentials are generated, never supplied.');
    const token = randomBytes(32).toString('hex');
    return Object.freeze({ token, nativeVerifier: createHash('sha256').update(token).digest('hex') });
}
