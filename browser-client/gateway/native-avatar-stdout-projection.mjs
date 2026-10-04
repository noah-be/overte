// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Diagnostic projection only. No native reads, browser messages or retained rows.
const MARKER = 'BROWSER_AVATAR_SAMPLE ';
const MAX_LINE_BYTES = 16 * 1024;
const MAX_ROWS = 512;
const COMMON = ['version', 'kind', 'at', 'interstitialState', 'interstitialSignalAgeMs'];
const SAMPLE_NUMBERS = ['batchMs', 'publishedPoseAgeMs', 'avatarBuildMs', 'jointNamesMs',
    'jointRotationsMs', 'jointTranslationsMs', 'postPublicationPoseDeltaMeters',
    'postPublicationProbeMs', 'peerPacketRateHz', 'peerGlobalPositionUpdateRateHz', 'peerSimulationRateHz',
    'capturedFixtureTargetDistanceMeters'];
const AUTHOR_NUMBERS = ['cachedMyAvatarSendRateHz', 'cachedAvatarMixerOutPps',
    'authorGlobalPositionOutboundKbps', 'authorLocalPositionOutboundKbps'];
const DELIVERY_KEYS = ['queued','writeInvoked','refused','lastAdmission','censored','writeReturnAccepted'];
const DELIVERY_ENUM = ['none','not-admitted','overflow','queued','socket-closed','authority-refused','inactive-refused','write-invoked'];
const count = value => Number.isSafeInteger(value) && value >= 0 && value <= 65535;
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && Object.keys(value).every(key => keys.includes(key));
function delivery(value) {
    return value === null || exact(value,DELIVERY_KEYS) && ['queued','writeInvoked','refused'].every(key=>count(value[key]))
        && DELIVERY_ENUM.includes(value.lastAdmission) && typeof value.censored === 'boolean' && value.writeReturnAccepted === null;
}
const GATEWAY_KEYS=['at','sequence','socketOpen','bufferedBytes','writeInvoked','writeReturnAccepted',
    'capturedFixtureTargetDistanceMeters','fixtureNameMatches','avatarProjectionCensored','observationCensored'];
function gatewayDelivery(value) {
    return value===null || exact(value,GATEWAY_KEYS) && Number.isSafeInteger(value.at) && value.at>=0
        && Number.isSafeInteger(value.sequence) && value.sequence>=1 && value.sequence<=128
        && typeof value.socketOpen==='boolean' && typeof value.writeInvoked==='boolean' && value.writeReturnAccepted===null
        && (value.bufferedBytes===null || Number.isSafeInteger(value.bufferedBytes) && value.bufferedBytes>=0 && value.bufferedBytes<=64*1024*1024)
        && bounded(value.capturedFixtureTargetDistanceMeters) && count(value.fixtureNameMatches) && value.fixtureNameMatches<=32
        && typeof value.avatarProjectionCensored==='boolean' && typeof value.observationCensored==='boolean'
        && (!value.writeInvoked || value.socketOpen && value.bufferedBytes !== null && value.bufferedBytes < 4*1024*1024)
        && (value.socketOpen || value.bufferedBytes===null && !value.writeInvoked)
        && (value.capturedFixtureTargetDistanceMeters===null || value.fixtureNameMatches===1 && !value.avatarProjectionCensored)
        && (!value.observationCensored || value.sequence===128)
        && (value.bufferedBytes===null || value.writeInvoked===(value.socketOpen && value.bufferedBytes<4*1024*1024));
}
const FLOW_KEYS=['version','at','sequence','censored','counts','ingress','offer','flight','pending','callback'];
const stamp=value=>Number.isSafeInteger(value) && value>=0;
const tuple=(value,length)=>Array.isArray(value) && value.length===length;
const nullableBool=value=>value===null || typeof value==='boolean';
const ownerCode=value=>value===0 || value===1;
const textBytes=value=>Number.isSafeInteger(value) && value>=0 && value<=48*1024*1024+1024;
function gatewayAvatarFlow(value) {
    if(value===null)return true;
    if(!exact(value,FLOW_KEYS) || value.version!==1 || !stamp(value.at) || !Number.isSafeInteger(value.sequence)
        || value.sequence<1 || value.sequence>128 || !tuple(value.censored,2) || !value.censored.every(v=>typeof v==='boolean'))return false;
    const measurements=['counts','ingress','offer','flight','pending','callback'];
    if(value.censored[1])return value.sequence===128 && measurements.every(key=>value[key]===null);
    if(!tuple(value.counts,9) || !value.counts.every(count))return false;
    if(value.ingress!==null && !(tuple(value.ingress,5) && stamp(value.ingress[0]) && bounded(value.ingress[1])
        && value.ingress.slice(2).every(nullableBool)))return false;
    if(!tuple(value.offer,3) || ![0,1,2,3].includes(value.offer[0]) || !(value.offer[1]===null || stamp(value.offer[1]))
        || !bounded(value.offer[2]) || value.offer[1]===null && value.offer[2]!==null
        || value.offer[0]===0 && (value.offer[1]!==null || value.offer[2]!==null)
        || value.offer[0]===1 && value.offer[1]===null)return false;
    for(const key of ['flight','pending'])if(value[key]!==null && !(tuple(value[key],4) && stamp(value[key][0])
        && textBytes(value[key][1]) && bounded(value[key][2]) && ownerCode(value[key][3])))return false;
    return value.callback===null || tuple(value.callback,4) && stamp(value.callback[0]) && textBytes(value.callback[1])
        && ownerCode(value.callback[2]) && ownerCode(value.callback[3]);
}
const decoder = new TextDecoder('utf-8', { fatal: true });
const bounded = value => value === null || typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 300000;

function project(line, mode) {
    let message = decoder.decode(line);
    const markerAt = message.indexOf(MARKER);
    if (markerAt < 0 || message.indexOf(MARKER, markerAt + MARKER.length) >= 0) return null;
    // Qt may decorate a raw message, or print its QString as a JSON-escaped string.
    if (message[markerAt - 1] === '"') {
        message = JSON.parse(message.slice(markerAt - 1).trim());
        if (typeof message !== 'string' || !message.startsWith(MARKER)) return null;
    } else message = message.slice(markerAt);
    const value = JSON.parse(message.slice(MARKER.length));
    if (!value || typeof value !== 'object' || Array.isArray(value)
        || !Number.isSafeInteger(value.at) || value.at < 0
        || !['unknown', 'active', 'inactive'].includes(value.interstitialState)
        || !bounded(value.interstitialSignalAgeMs)) return null;
    let keys;
    if (value.kind === 'sample') {
        if(value.version!==(mode==='native-child'?1:2) || mode==='gateway-log' && !gatewayAvatarFlow(value.gatewayAvatarFlow))return null;
        if (!Number.isSafeInteger(value.sequence) || value.sequence < 1 || value.sequence > MAX_ROWS
            || !['self', 'fixture-peer'].includes(value.role) || !SAMPLE_NUMBERS.every(key => bounded(value[key])) || !delivery(value.nativeDelivery) || !gatewayDelivery(value.gatewayDelivery)) return null;
        if (value.role !== 'fixture-peer' && value.capturedFixtureTargetDistanceMeters !== null) return null;
        keys = [...COMMON, 'sequence', 'role', ...SAMPLE_NUMBERS, 'nativeDelivery', 'gatewayDelivery', ...(mode==='gateway-log'?['gatewayAvatarFlow']:[])];
    } else if (value.kind === 'author-transmission') {
        if(value.version!==1)return null;
        if (value.statsFreshness !== 'not-forced-or-established' || !AUTHOR_NUMBERS.every(key => bounded(value[key]))) return null;
        keys = [...COMMON, 'statsFreshness', ...AUTHOR_NUMBERS];
    } else return null;
    if (Object.keys(value).length !== keys.length || !Object.keys(value).every(key => keys.includes(key))) return null;
    // Reconstruct; never forward original text, decorator, property order or errors.
    return Object.fromEntries(keys.map(key => [key, value[key]]));
}

export function attachNativeAvatarProjection(child, { enabled, publicPlace, emit, mode = 'native-child' }) {
    if (enabled !== true || publicPlace !== false || typeof emit !== 'function' || !['native-child','gateway-log'].includes(mode)) return;
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
                    const value = project(pending.subarray(0, length),mode);
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
