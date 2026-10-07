// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/**
 * Test-only observation of the native UDT and two-byte NL headers. Never copies
 * payloads, source IDs, HMACs or addresses and never changes packet bytes.
 * Layout: libraries/networking/src/udt/{Packet,ControlPacket}.cpp and NLPacket.
 * The factory is self-contained so Playwright can install it before app boot.
 */
export function createHeaderObserver() {
    const MODULUS = 0x8000000, HALF = MODULUS / 2, WINDOW = 65536;
    const MAX_MESSAGES = 32, MAX_PARTS = 65536, MAX_RANGES = 256;
    const keys = [[0, 0], [0x74, 0x65], [0x61, 0x64], [0x6e, 0x61]];
    const counts = { packets: 0, malformed: 0, nonBinary: 0, data: 0, reliable: 0, unreliable: 0,
        uniqueReliable: 0, repeatedReliable: 0, outOfOrderReliable: 0,
        forwardGapEvents: 0, introducedGapPackets: 0, recoveredGapPackets: 0,
        untrackedGapPackets: 0, messagePackets: 0, wirePartsComplete: 0,
        messageEvictions: 0, reobservedEvictedMessages: 0, untrackedCompletionIdentities: 0,
        unsupportedParts: 0, handshakes: 0, handshakeResets: 0,
        ackPackets: 0, repeatedAcks: 0, ackAdvances: 0, ackRegressions: 0, untrackedPacketTypes: 0 };
    const controlTypes = [0, 0, 0, 0], obfuscationLevels = [0, 0, 0, 0], packetTypes = {};
    const seen = new Uint32Array(WINDOW); seen.fill(0xffffffff);
    const messageHistory = new Uint32Array(4096); messageHistory.fill(0xffffffff);
    const completedHistory = new Uint8Array(4096);
    let highest, initial, latestAck, ackOrdinal, lastAckAtMs, packetTypeCount = 0;
    const gaps = [], messages = new Map();
    const signedDelta = (left, right) => ((left - right + HALF + MODULUS) % MODULUS) - HALF;
    const normalize = ordinal => (ordinal % MODULUS + MODULUS) % MODULUS;
    const containsPart = (message, part) => Boolean(message.parts[part >>> 3] & (1 << (part & 7)));
    const atMs = () => typeof performance === 'object' ? performance.now() : 0;
    function removeGap(ordinal) {
        for (let index = 0; index < gaps.length; index++) {
            const [first, last] = gaps[index];
            if (ordinal < first || ordinal > last) continue;
            if (first === last) gaps.splice(index, 1);
            else if (ordinal === first) gaps[index][0]++;
            else if (ordinal === last) gaps[index][1]--;
            else {
                gaps[index][1] = ordinal - 1;
                if (gaps.length < MAX_RANGES) gaps.splice(index + 1, 0, [ordinal + 1, last]);
                else counts.untrackedGapPackets += last - ordinal;
            }
            counts.recoveredGapPackets++; return true;
        }
        return false;
    }
    function reliable(sequence) {
        if (seen[sequence % WINDOW] === sequence) { counts.repeatedReliable++; return; }
        seen[sequence % WINDOW] = sequence; counts.uniqueReliable++;
        if (highest === undefined) { highest = sequence; return; }
        const delta = signedDelta(sequence, normalize(highest)), ordinal = highest + delta;
        if (delta > 0) {
            if (delta > 1) {
                counts.forwardGapEvents++; counts.introducedGapPackets += delta - 1;
                if (gaps.length < MAX_RANGES) gaps.push([highest + 1, ordinal - 1]);
                else counts.untrackedGapPackets += delta - 1;
            }
            highest = ordinal;
        } else {
            counts.outOfOrderReliable++;
            removeGap(ordinal);
        }
    }
    function messageHeader(number, part, position, packetType, bytes) {
        if (part >= MAX_PARTS) { counts.unsupportedParts++; return; }
        let message = messages.get(number);
        if (!message) {
            if (messages.size >= MAX_MESSAGES) { messages.delete(messages.keys().next().value); counts.messageEvictions++; }
            const historyIndex = number % messageHistory.length, historyIncomplete = messageHistory[historyIndex] === number;
            if (historyIncomplete) counts.reobservedEvictedMessages++;
            else { messageHistory[historyIndex] = number; completedHistory[historyIndex] = 0; }
            message = { number, packetType, firstObservedAtMs: atMs(), lastObservedAtMs: 0, packets: 0,
                datagramBytes: 0, uniqueParts: 0, repeatedParts: 0, highestPart: -1, contiguousThrough: -1,
                lastPart: null, firstSeen: false, lastSeen: false, complete: false, positions: [0, 0, 0, 0],
                historyIncomplete, parts: new Uint8Array(MAX_PARTS / 8) };
            messages.set(number, message);
        }
        message.lastObservedAtMs = atMs(); message.packets++; message.datagramBytes += bytes;
        message.positions[position]++; message.highestPart = Math.max(message.highestPart, part);
        if (position === 2 || position === 0) message.firstSeen = true;
        if (position === 1 || position === 0) { message.lastSeen = true; message.lastPart = part; }
        if (containsPart(message, part)) message.repeatedParts++;
        else { message.parts[part >>> 3] |= 1 << (part & 7); message.uniqueParts++; }
        while (message.contiguousThrough + 1 < MAX_PARTS && containsPart(message, message.contiguousThrough + 1)) message.contiguousThrough++;
        if (!message.complete && message.lastSeen && message.contiguousThrough >= message.lastPart) {
            message.complete = true;
            const historyIndex = number % messageHistory.length;
            if (messageHistory[historyIndex] !== number) counts.untrackedCompletionIdentities++;
            else if (!completedHistory[historyIndex]) { counts.wirePartsComplete++; completedHistory[historyIndex] = 1; }
        }
    }
    function accept(value) {
        let view;
        if (value instanceof ArrayBuffer) view = new DataView(value);
        else if (ArrayBuffer.isView(value)) view = new DataView(value.buffer, value.byteOffset, value.byteLength);
        else { counts.nonBinary++; return; }
        counts.packets++;
        if (view.byteLength < 4 || view.byteLength > 1424) { counts.malformed++; return; }
        const flags = view.getUint32(0, true);
        if (flags & 0x80000000) {
            const type = (flags & 0x7fffffff) >>> 16;
            if (type > 3 || (type !== 3 && view.byteLength < 8)) { counts.malformed++; return; }
            controlTypes[type]++;
            if (type === 1) {
                const sequence = view.getUint32(4, true) & (MODULUS - 1); counts.handshakes++;
                if (initial !== sequence) {
                    if (initial !== undefined) counts.handshakeResets++;
                    initial = sequence; highest = sequence - 1; gaps.length = 0;
                    seen.fill(0xffffffff); messages.clear(); messageHistory.fill(0xffffffff); completedHistory.fill(0);
                }
            }
            if (type === 0) {
                const sequence = view.getUint32(4, true) & (MODULUS - 1); counts.ackPackets++;
                if (latestAck !== undefined) {
                    const delta = signedDelta(sequence, latestAck);
                    if (delta === 0) counts.repeatedAcks++;
                    else if (delta > 0) counts.ackAdvances++;
                    else counts.ackRegressions++;
                    ackOrdinal += delta;
                } else ackOrdinal = sequence;
                latestAck = sequence; lastAckAtMs = atMs();
            }
            return;
        }
        const isMessage = Boolean(flags & 0x20000000), offset = isMessage ? 12 : 4;
        if (view.byteLength < offset + 2) { counts.malformed++; return; }
        counts.data++;
        const level = (flags >>> 27) & 3; obfuscationLevels[level]++;
        // Only the two NL type/version bytes are unobfuscated, not source/HMAC/payload.
        const packetType = view.getUint8(offset) ^ keys[level][0];
        const version = view.getUint8(offset + 1) ^ keys[level][1];
        const typeKey = `${packetType}:${version}`;
        if (Object.hasOwn(packetTypes, typeKey)) packetTypes[typeKey]++;
        else if (packetTypeCount < 64) { packetTypes[typeKey] = 1; packetTypeCount++; }
        else counts.untrackedPacketTypes++;
        if (flags & 0x40000000) { counts.reliable++; reliable(flags & (MODULUS - 1)); }
        else counts.unreliable++;
        if (isMessage) {
            counts.messagePackets++;
            const bits = view.getUint32(4, true);
            messageHeader(bits & 0x3fffffff, view.getUint32(8, true), bits >>> 30, packetType, view.byteLength);
        }
    }
    function snapshot() {
        const outstanding = gaps.reduce((total, [first, last]) => total + last - first + 1, 0);
        return { ...counts, highestReliableSequence: highest === undefined ? null : normalize(highest),
            handshakeInitialSequence: initial ?? null, trackedMissingSequences: outstanding,
            missingSequenceRanges: gaps.slice(0, 16).map(([first, last]) => ({ first: normalize(first), last: normalize(last), count: last - first + 1 })),
            retainedMissingRanges: gaps.length, obfuscationLevels: [...obfuscationLevels],
            controlTypes: [...controlTypes], packetTypes: { ...packetTypes },
            ackFrontier: latestAck ?? null, ackOrdinal: ackOrdinal ?? null, lastAckAtMs: lastAckAtMs ?? null,
            messages: [...messages.values()].map(({ parts, ...message }) => ({ ...message,
                expectedParts: message.lastPart === null ? null : message.lastPart + 1,
                missingParts: message.historyIncomplete ? null : Math.max(0, (message.lastPart ?? message.highestPart) + 1 - message.uniqueParts),
                partsBeyondLast: message.lastPart !== null && message.highestPart > message.lastPart,
                firstMissingPart: message.complete || message.historyIncomplete ? null : message.contiguousThrough + 1 })),
            limits: { sequenceWindow: WINDOW, messages: MAX_MESSAGES, partsPerMessage: MAX_PARTS, messageIdentityHistory: messageHistory.length,
                gapRanges: MAX_RANGES, emittedGapRanges: 16, packetTypeVersions: 64 },
            scope: 'Observed native headers only. Repeated sequence/part means observed duplicate or retransmission. Wire parts complete does not prove SDK/application delivery. Evicted messages and untracked gaps are explicit.' };
    }
    return { accept, snapshot };
}
