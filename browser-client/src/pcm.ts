// SPDX-License-Identifier: Apache-2.0
/** Encode clipped floating-point audio as the gateway's explicit little-endian PCM. */
export function encodePCM(samples: ArrayLike<number>): ArrayBuffer {
    const data = new ArrayBuffer(samples.length * 2);
    const view = new DataView(data);
    for (let i = 0; i < samples.length; i++) {
        const value = Number.isFinite(samples[i]) ? Math.max(-1, Math.min(1, samples[i])) : 0;
        view.setInt16(i * 2, Math.round(value < 0 ? value * 32768 : value * 32767), true);
    }
    return data;
}

export function decodePCM(data: ArrayBuffer): Float32Array {
    if (data.byteLength % 2) throw new Error('Incomplete PCM sample');
    const view = new DataView(data);
    const result = new Float32Array(data.byteLength / 2);
    for (let i = 0; i < result.length; i++) result[i] = view.getInt16(i * 2, true) / 32768;
    return result;
}
