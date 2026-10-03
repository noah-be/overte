// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { ASSET_REPLY_HEADER_BYTES, MAX_ASSET_BYTES } from './native-assets';

export const MAX_RELIABLE_MESSAGE_BYTES = MAX_ASSET_BYTES + ASSET_REPLY_HEADER_BYTES;

/** Assemble reliable native messages with one final allocation. The historical
 * SDK copied the entire accumulated message on every packet (quadratic work). */
export class MessageAssembler {
    private readonly parts: Uint8Array[] = [];
    private size = 0;
    constructor(private readonly limit = MAX_RELIABLE_MESSAGE_BYTES) {}

    append(part: Uint8Array): void {
        if (this.size + part.byteLength > this.limit || this.parts.length >= 65536) {
            throw new Error('The server message exceeds the browser receive limit.');
        }
        this.parts.push(part);
        this.size += part.byteLength;
    }

    finish(): Uint8Array {
        const joined = new Uint8Array(this.size);
        let offset = 0;
        for (const part of this.parts) {
            joined.set(part, offset);
            offset += part.byteLength;
        }
        this.parts.length = 0;
        this.size = 0;
        return joined;
    }
}
