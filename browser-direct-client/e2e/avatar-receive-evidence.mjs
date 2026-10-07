// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Test-only first-record inspection, before SDK receive. This is not packet
 * authentication or a complete BulkAvatarData decoder. Layout and XOR keys:
 * native udt/Packet.cpp, NLPacket.cpp and AvatarMixerWorker.cpp.
 * Self-contained for Worker.evaluate; no input mutation or payload retention. */
export function createAvatarReceiveObserver(expectedNativeID) {
    const canonical = value => typeof value === 'string' && /^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(value)
        && value.startsWith('{') === value.endsWith('}') ? value.replace(/[{}-]/g, '').toLowerCase() : null;
    const identity = canonical(expectedNativeID);
    if (!identity || /^0+$/.test(identity)) throw new Error('A privately qualified native participant is required.');
    const expectedBytes = Uint8Array.from(identity.match(/../g), value => parseInt(value, 16));
    const keys = [[0, 0, 0, 0, 0, 0, 0, 0], [0x74, 0x65, 0x73, 0x73, 0x69, 0x72, 0x62, 0x63],
        [0x61, 0x64, 0x72, 0x61, 0x72, 0x69, 0x62, 0x73], [0x6e, 0x61, 0x6d, 0x66, 0x66, 0x75, 0x68, 0x72]];
    const counts = { packets: 0, nonBinary: 0, oversized: 0, truncated: 0, control: 0,
        otherTypes: 0, bulkPackets: 0, wrongVersion: 0, unsupportedFragments: 0,
        unsupportedFlags: 0, firstRecordNativeMatches: 0, firstRecordOtherPeer: 0,
        noGlobalPosition: 0, nonFinitePosition: 0, positions: 0, positionChanges: 0,
        jointDataPackets: 0, jointDefaultFlagPackets: 0, flagChanges: 0, bodyChecksumChanges: 0,
        jointChecksumChanges: 0, unsupportedBodyLayout: 0, sampleEvictions: 0 };
    const samples = [], obfuscationLevels = [0, 0, 0, 0];
    let first = null, last = null;
    const copy = sample => sample ? { ...sample, position: { ...sample.position } } : null;
    // Bounded extent reader, not a value decoder. No fields/UUIDs are retained.
    // AvatarData.cpp toByteArray and AvatarDataPacket section sizes are the
    // authority; checksums stop at this first record, even with later records.
    function extent(view, body, flags) {
        let cursor = body + 18, jointStart = null, jointEnd = null;
        const skip = length => { if (cursor + length > view.byteLength) throw new RangeError(); cursor += length; };
        const byte = () => { skip(1); return view.getUint8(cursor - 1); };
        const bitCount = number => {
            const begin = cursor; skip(Math.ceil(number / 8)); let count = 0;
            for (let index = 0; index < number; index++) if (view.getUint8(begin + (index >>> 3)) & (1 << (index % 8))) count++;
            return count;
        };
        const fixed = [12, 24, 6, 2, 12, 1, 20, 2, 18, 12, 24];
        for (let bit = 0; bit < fixed.length; bit++) if (flags & (1 << bit)) skip(fixed[bit]);
        if (flags & 0x800) { skip(16); skip(byte() * 4); }
        if (flags & 0x1000) {
            jointStart = cursor;
            const number = byte(); skip(bitCount(number) * 6);
            const translations = bitCount(number); skip(4); skip(translations * 6);
            if (flags & 0x4000) skip(84);
            jointEnd = cursor;
        } else if (flags & 0x4000) return null;
        if (flags & 0x2000) { const number = byte(); skip(2 * Math.ceil(number / 8)); }
        return { end: cursor, jointStart, jointEnd };
    }
    // Non-cryptographic change indicator only. Hash input never includes the
    // verified NL header or first session UUID; original bytes are not emitted.
    function checksum(view, begin, end) {
        let value = 0x811c9dc5;
        for (let index = begin; index < end; index++) value = Math.imul(value ^ view.getUint8(index), 0x01000193) >>> 0;
        return value.toString(16).padStart(8, '0');
    }
    function accept(value) {
        let input;
        if (value instanceof ArrayBuffer) input = new DataView(value);
        else if (ArrayBuffer.isView(value)) input = new DataView(value.buffer, value.byteOffset, value.byteLength);
        else { counts.nonBinary++; return; }
        counts.packets++;
        // Check before allocating/copying anything from the real datagram.
        if (input.byteLength > 1424) { counts.oversized++; return; }
        if (input.byteLength < 4) { counts.truncated++; return; }
        const flags = input.getUint32(0, true);
        if (flags & 0x80000000) { counts.control++; return; }
        const message = Boolean(flags & 0x20000000), udtBytes = message ? 12 : 4;
        if (input.byteLength < udtBytes + 2) { counts.truncated++; return; }
        const level = (flags >>> 27) & 3, bytes = new Uint8Array(input.buffer, input.byteOffset, input.byteLength).slice();
        for (let index = udtBytes; index < bytes.length; index++) bytes[index] ^= keys[level][(index - udtBytes) % 8];
        const view = new DataView(bytes.buffer);
        if (view.getUint8(udtBytes) !== 11) { counts.otherTypes++; return; }
        counts.bulkPackets++; obfuscationLevels[level]++;
        if (view.getUint8(udtBytes + 1) !== 55) { counts.wrongVersion++; return; }
        // FIRST/MIDDLE/LAST are not standalone record starts. ONLY must be part0.
        if (message && (view.getUint32(4, true) >>> 30 !== 0 || view.getUint32(8, true) !== 0)) {
            counts.unsupportedFragments++; return;
        }
        const body = udtBytes + 20; // verified NL type/version + source2 + HMAC16
        if (view.byteLength < body + 18) { counts.truncated++; return; }
        let matches = true;
        for (let index = 0; index < 16; index++) if (view.getUint8(body + index) !== expectedBytes[index]) matches = false;
        if (!matches) { counts.firstRecordOtherPeer++; return; }
        counts.firstRecordNativeMatches++;
        const avatarFlags = view.getUint16(body + 16, true);
        if (avatarFlags & ~0x7fff) { counts.unsupportedFlags++; return; }
        if (avatarFlags & 0x1000) counts.jointDataPackets++;
        if (avatarFlags & 0x2000) counts.jointDefaultFlagPackets++;
        if (!(avatarFlags & 1)) { counts.noGlobalPosition++; return; }
        if (view.byteLength < body + 30) { counts.truncated++; return; }
        const position = { x: view.getFloat32(body + 18, true), y: view.getFloat32(body + 22, true), z: view.getFloat32(body + 26, true) };
        if (!Object.values(position).every(Number.isFinite)) { counts.nonFinitePosition++; return; }
        let record;
        try { record = extent(view, body, avatarFlags); } catch { counts.truncated++; return; }
        if (!record) { counts.unsupportedBodyLayout++; return; }
        const bodyChecksum = checksum(view, body + 16, record.end);
        const jointChecksum = record.jointStart === null ? null : checksum(view, record.jointStart, record.jointEnd);
        const sample = { atMs: performance.now(), observedAtUnixMs: Date.now(), position,
            avatarFlags, reliable: Boolean(flags & 0x40000000), message, obfuscationLevel: level,
            firstRecordNativeIdentityMatched: true, bodyChecksum, jointChecksum,
            checksumAlgorithm: 'FNV1a32 change indicator', firstBodyBytes: record.end - body - 16,
            trailingRecordBytes: view.byteLength - record.end };
        counts.positions++;
        if (last && ['x', 'y', 'z'].some(axis => last.position[axis] !== position[axis])) counts.positionChanges++;
        if (last && last.avatarFlags !== avatarFlags) counts.flagChanges++;
        if (last && last.bodyChecksum !== bodyChecksum) counts.bodyChecksumChanges++;
        if (last?.jointChecksum && jointChecksum && last.jointChecksum !== jointChecksum) counts.jointChecksumChanges++;
        if (!first) first = copy(sample);
        last = copy(sample);
        if (samples.length >= 64) { samples.shift(); counts.sampleEvictions++; }
        samples.push(sample);
    }
    return Object.freeze({ accept, snapshot: () => ({ ...counts, obfuscationLevels: [...obfuscationLevels],
        limits: { maxDatagramBytes: 1424, retainedSamples: 64, firstRecordOnly: true },
        authenticationObserved: false, authenticationOrDeliveryChanged: false,
        scope: 'Finite global position/flags and bounded first-record body/joint-section change checksums in BulkAvatarData11:55. Complete ordinary datagrams or ONLY part0; no joint value decoding or authentication decision. Checksums exclude NL/source/HMAC/leadingUUID and later avatar records.',
        first: copy(first), last: copy(last), samples: samples.map(copy) }) });
}
