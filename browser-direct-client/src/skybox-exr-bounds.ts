// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Inspect the OpenEXR image window before the stock loader can allocate its
 * decoded pixels. Reject unsupported multipart/oversize data without resampling. */
export function validateSkyboxEXR(bytes: ArrayBuffer, maximumDimension: number, maximumDecodedBytes = 128 * 1024 * 1024): void {
    const view = new DataView(bytes);
    if (view.byteLength < 8 || view.getUint32(0, true) !== 20000630) throw Error('Invalid skybox OpenEXR header');
    if (view.getUint32(4, true) & (1 << 12)) throw Error('Multipart skybox OpenEXR is unsupported');
    let offset = 8;
    const name = (): string => {
        const start = offset;
        while (offset < view.byteLength && offset < 65536 && view.getUint8(offset) !== 0) offset++;
        if (offset >= view.byteLength || offset >= 65536) throw Error('Skybox OpenEXR header exceeds its bound');
        const value = new TextDecoder('ascii').decode(new Uint8Array(bytes, start, offset - start)); offset++; return value;
    };
    for (let attributes = 0; attributes < 256; attributes++) {
        const key = name();
        if (!key) break;
        const type = name();
        if (offset + 4 > view.byteLength) throw Error('Truncated skybox OpenEXR header');
        const size = view.getUint32(offset, true); offset += 4;
        if (size > 65536 || offset + size > Math.min(view.byteLength, 65536)) throw Error('Skybox OpenEXR attribute exceeds its bound');
        if (key === 'dataWindow') {
            if (type !== 'box2i' || size !== 16) throw Error('Invalid skybox OpenEXR image window');
            const width = view.getInt32(offset + 8, true) - view.getInt32(offset, true) + 1;
            const height = view.getInt32(offset + 12, true) - view.getInt32(offset + 4, true) + 1;
            if (width < 1 || height < 1 || width > maximumDimension || height > maximumDimension || width * height * 8 > maximumDecodedBytes) throw Error('Skybox OpenEXR exceeds the browser image bounds');
            return;
        }
        offset += size;
    }
    throw Error('Skybox OpenEXR has no bounded image window');
}
