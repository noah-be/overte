// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Diagnostic projection only. No native reads, browser messages or retained rows.
const MARKER = 'BROWSER_AVATAR_SAMPLE ';
const MAX_LINE_BYTES = 16 * 1024;
const MAX_ROWS = 512;
const COMMON = ['version', 'kind', 'at', 'interstitialState', 'interstitialSignalAgeMs'];
const SAMPLE_NUMBERS = ['batchMs', 'publishedPoseAgeMs', 'avatarBuildMs', 'jointNamesMs',
    'jointRotationsMs', 'jointTranslationsMs', 'postPublicationPoseDeltaMeters',
    'postPublicationProbeMs', 'peerPacketRateHz', 'peerGlobalPositionUpdateRateHz', 'peerSimulationRateHz'];
const AUTHOR_NUMBERS = ['cachedMyAvatarSendRateHz', 'cachedAvatarMixerOutPps',
    'authorGlobalPositionOutboundKbps', 'authorLocalPositionOutboundKbps'];
const decoder = new TextDecoder('utf-8', { fatal: true });
const bounded = value => value === null || typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 300000;

function project(line) {
    let message = decoder.decode(line);
    const markerAt = message.indexOf(MARKER);
    if (markerAt < 0 || message.indexOf(MARKER, markerAt + MARKER.length) >= 0) return null;
    // Qt may decorate a raw message, or print its QString as a JSON-escaped string.
    if (message[markerAt - 1] === '"') {
        message = JSON.parse(message.slice(markerAt - 1).trim());
        if (typeof message !== 'string' || !message.startsWith(MARKER)) return null;
    } else message = message.slice(markerAt);
    const value = JSON.parse(message.slice(MARKER.length));
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.version !== 1
        || !Number.isSafeInteger(value.at) || value.at < 0
        || !['unknown', 'active', 'inactive'].includes(value.interstitialState)
        || !bounded(value.interstitialSignalAgeMs)) return null;
    let keys;
    if (value.kind === 'sample') {
        if (!Number.isSafeInteger(value.sequence) || value.sequence < 1 || value.sequence > MAX_ROWS
            || !['self', 'fixture-peer'].includes(value.role) || !SAMPLE_NUMBERS.every(key => bounded(value[key]))) return null;
        keys = [...COMMON, 'sequence', 'role', ...SAMPLE_NUMBERS];
    } else if (value.kind === 'author-transmission') {
        if (value.statsFreshness !== 'not-forced-or-established' || !AUTHOR_NUMBERS.every(key => bounded(value[key]))) return null;
        keys = [...COMMON, 'statsFreshness', ...AUTHOR_NUMBERS];
    } else return null;
    if (Object.keys(value).length !== keys.length || !Object.keys(value).every(key => keys.includes(key))) return null;
    // Reconstruct; never forward original text, decorator, property order or errors.
    return Object.fromEntries(keys.map(key => [key, value[key]]));
}

export function attachNativeAvatarProjection(child, { enabled, publicPlace, emit }) {
    if (enabled !== true || publicPlace !== false || typeof emit !== 'function') return;
    const pending = Buffer.alloc(MAX_LINE_BYTES);
    let length = 0, dropping = false, rows = 0, closed = false;
    const close = () => { closed = true; length = 0; dropping = false; pending.fill(0); child.stdout.removeListener('data', receive); };
    function receive(data) {
        if (closed || !Buffer.isBuffer(data)) return;
        let offset = 0;
        while (offset < data.length && !closed) {
            const newline = data.indexOf(10, offset);
            const end = newline < 0 ? data.length : newline;
            const segmentLength = end - offset;
            if (!dropping && length + segmentLength <= MAX_LINE_BYTES) {
                data.copy(pending, length, offset, end); length += segmentLength;
            } else { dropping = true; length = 0; }
            if (newline < 0) break;
            if (!dropping) {
                try {
                    const value = project(pending.subarray(0, length));
                    if (value) {
                        rows++;
                        try { emit(MARKER + JSON.stringify(value) + '\n'); } catch { /* Diagnostics cannot change session outcome. */ }
                        if (rows >= MAX_ROWS) close();
                    }
                } catch { /* Malformed/private input is discarded without reflection. */ }
            }
            length = 0; dropping = false; offset = newline + 1;
        }
    }
    child.stdout.on('data', receive);
    child.once('close', close);
}
