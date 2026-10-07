// SPDX-License-Identifier: Apache-2.0
export interface NativeAdminCredential {
    /** Fresh 32-byte CSPRNG machine credential, encoded as 64 hexadecimal characters. */
    readonly token: string;
    /** SHA-256 hexadecimal verifier required by native DomainServer HTTP Basic. */
    readonly nativeVerifier: string;
}

/** Generates a native machine credential; caller-supplied secrets are never accepted. */
export function nativeAdminCredential(): NativeAdminCredential;
