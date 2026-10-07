// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0

export const MAX_ASSET_BYTES = 64 * 1024 * 1024;
export const ASSET_REPLY_HEADER_BYTES = 45;
const hashPattern = /^[a-f0-9]{64}$/;

export function nativeAssetGetBody(id: number, hash: string): Uint8Array {
    if (!hashPattern.test(hash)) throw new Error('Invalid native asset hash.');
    const body = new Uint8Array(52), view = new DataView(body.buffer);
    view.setUint32(0, id, true);
    body.set(Uint8Array.from(hash.match(/../g)!.map((byte) => parseInt(byte, 16))), 4);
    // ByteRange [0, 0] is the native complete-file request.
    view.setBigInt64(36, 0n, true); view.setBigInt64(44, 0n, true);
    return body;
}

function hashAt(data: DataView, offset: number): string {
    return [...new Uint8Array(data.buffer, data.byteOffset + offset, 32)]
        .map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function nativeAssetMapping(data: DataView, id: number): { hash: string; redirectedPath?: string } {
    if (data.byteLength < 5 || data.getUint32(0, true) !== id) throw new Error('Invalid ATP mapping response.');
    if (data.getUint8(4) !== 0) throw new Error('The ATP path was not found or access was denied.');
    if (data.byteLength < 38) throw new Error('The ATP mapping response was truncated.');
    const hash = hashAt(data, 5);
    const redirect = data.getUint8(37);
    if (redirect === 0) return { hash };
    if (redirect !== 1 || data.byteLength < 42) throw new Error('Invalid ATP redirect.');
    const size = data.getUint32(38, true);
    if (size === 0 || size > 4096 || 42 + size !== data.byteLength) throw new Error('Invalid ATP redirect path.');
    const redirectedPath = new TextDecoder('utf-8', { fatal: true }).decode(
        new Uint8Array(data.buffer, data.byteOffset + 42, size));
    if (!redirectedPath.startsWith('/') || redirectedPath.includes('\0') || redirectedPath.split('/').includes('..')) {
        throw new Error('Invalid ATP redirect path.');
    }
    return { hash, redirectedPath };
}

export function nativeAssetReply(data: DataView, id: number, expectedHash: string): ArrayBuffer {
    if (data.byteLength < 37 || data.getUint32(32, true) !== id || hashAt(data, 0) !== expectedHash) {
        throw new Error('Invalid ATP asset response.');
    }
    if (data.getUint8(36) !== 0) throw new Error('The ATP asset was not found or access was denied.');
    if (data.byteLength < ASSET_REPLY_HEADER_BYTES) throw new Error('The ATP asset response was truncated.');
    const size = Number(data.getBigInt64(37, true));
    if (!Number.isSafeInteger(size) || size < 0 || size > MAX_ASSET_BYTES || size !== data.byteLength - ASSET_REPLY_HEADER_BYTES) {
        throw new Error('The ATP asset returned an invalid size.');
    }
    return data.buffer.slice(data.byteOffset + ASSET_REPLY_HEADER_BYTES,
        data.byteOffset + ASSET_REPLY_HEADER_BYTES + size) as ArrayBuffer;
}
