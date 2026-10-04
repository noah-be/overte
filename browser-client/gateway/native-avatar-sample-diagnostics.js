// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Managed laboratory opt-in. Private fixed-enum/numeric stdout only; no protocol fields.
function createNativeAvatarSampleDiagnostics(config) {
    'use strict';
    var now = config.now || function () { return Date.now(); };
    var passive = config.mode === 'passive';
    var stopped = false, emitted = 0, sequence = 0, rows = [], batchStarted = 0, lastBatch = null, tracking = false, batchAuthority;
    var mode = 'unknown', signalAt = null, connected = false;
    function current() { try { return !stopped && config.current() && (typeof config.authority !== 'function' || !!batchAuthority && config.authority() === batchAuthority); } catch (error) { return false; } }
    function number(value) { return typeof value === 'number' && isFinite(value) && value >= 0 && value <= 300000 ? value : null; }
    function elapsed(start) { return typeof start === 'number' ? number(now() - start) : null; }
    function changed(value) { if (!stopped && typeof value === 'boolean') { mode = value ? 'active' : 'inactive'; signalAt = now(); } }
    try {
        if (config.window && config.window.interstitialModeChanged && typeof config.window.interstitialModeChanged.connect === 'function') {
            config.window.interstitialModeChanged.connect(changed); connected = true;
        }
    } catch (error) { /* Unavailable is not an inferred native state. */ }
    function signalState() { return { interstitialState: mode, interstitialSignalAgeMs: elapsed(signalAt) }; }
    function print(value) {
        if (!current() || emitted >= 512) return;
        try { config.print('BROWSER_AVATAR_SAMPLE ' + JSON.stringify(value)); emitted++; } catch (error) { /* Never reflect private exceptions. */ }
    }
    function rate(id, name) {
        // ScriptAvatar is a QObject wrapper, not AvatarData. Its native update
        // counters are exposed on AvatarList (AvatarManager), not the wrapper.
        if (typeof id !== 'string') return null;
        var uuid = id.length === 38 && id.charAt(0) === '{' && id.charAt(37) === '}' ? id.slice(1,-1) : id;
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)
            || uuid === '00000000-0000-0000-0000-000000000000') return null;
        try { var owner = config.avatarList;
            if (!current() || !owner) return null;
            var method = arguments[2] === true ? 'getAvatarSimulationRate' : 'getAvatarUpdateRate';
            var read = owner[method];
            return current() && typeof read === 'function' ? number(read.call(owner, id, name)) : null; }
        catch (error) { return null; }
    }
    function authorRate(name) {
        // RateCounter readback may roll its averaging interval; it never sends a packet.
        try {
            if (!current() || !config.avatar) return null;
            var owner = config.avatar, read = owner.getDataRate;
            return current() && typeof read === 'function' ? number(read.call(owner, name)) : null;
        } catch (error) { return null; }
    }
    function stats(name) {
        try { return config.stats ? number(config.stats[name]) : null; } catch (error) { return null; }
    }
    function capturedFixtureTargetDistance(row) {
        // The Core fixture target is fixed. This reads only the already captured
        // browser DTO; it is not a native pose or packet-content readback.
        if (row.role !== 'fixture-peer' || !current()) return null;
        try {
            var position = row.result.position;
            if (!position || typeof position !== 'object') return null;
            var x = position.x, y = position.y, z = position.z;
            if (!current() || ![x,y,z].every(function (value) { return typeof value === 'number' && isFinite(value); })) return null;
            return number(Math.sqrt(Math.pow(x-4,2)+Math.pow(y-1.8,2)+Math.pow(z-2,2)));
        } catch (error) { return null; }
    }
    function stop() {
        if (stopped) return;
        stopped = true; rows = []; batchAuthority = undefined; tracking = false;
        try { if (connected) config.window.interstitialModeChanged.disconnect(changed); } catch (error) {}
        connected = false;
    }
    return {
        beginBatch: function () {
            rows = []; tracking = false;
            try { batchAuthority = typeof config.authority === 'function' ? config.authority() : undefined; } catch (error) { batchAuthority = undefined; }
            var time = now();
            if (current() && emitted < 512 && sequence < 512 && (lastBatch === null || time-lastBatch >= 500)) {
                batchStarted = time; lastBatch = time; sequence++; tracking = true;
            }
        },
        beginAvatar: function () {
            if (!tracking || !current() || emitted >= 512 || rows.length >= 32) return null;
            var row = { started: now(), poseAt: null, names: null, rotations: null, translations: null, phaseAt: null };
            rows.push(row); return row;
        },
        poseSampled: function (row) { if (row) row.poseAt = now(); },
        beginPhase: function (row) { if (row) row.phaseAt = now(); },
        endPhase: function (row, phase) {
            if (row && ['names','rotations','translations'].indexOf(phase) !== -1) { row[phase] = elapsed(row.phaseAt); row.phaseAt = null; }
        },
        completed: function (row, result, self, avatar) {
            if (!row) return;
            row.role = self ? 'self' : result.displayName === 'Native-Lab-Participant' ? 'fixture-peer' : 'other';
            if (row.role !== 'other') { row.result = result; row.avatar = passive ? null : avatar; row.completedAt = now(); }
        },
        published: function () {
            var batch = rows; rows = []; tracking = false;
            if (!current() || emitted >= 512) return;
            var publicationAt = now(), batchMs = elapsed(batchStarted);
            // Full mode probes only after original send/flush. Passive mode performs
            // no extra avatar/manager/Stats reads and leaves those fields unknown.
            // Neither mode replaces the already-published pose.
            batch.forEach(function (row) {
                if (!current() || emitted >= 512 || !row.result) return;
                var distance = null, packetRate = null, positionRate = null, simulationRate = null, probeStarted = passive ? null : now();
                if (!passive) try {
                    var fresh = row.avatar.position, old = row.result.position;
                    if (fresh && old && [fresh.x,fresh.y,fresh.z,old.x,old.y,old.z].every(function (n) { return typeof n === 'number' && isFinite(n); })) {
                        distance = number(Math.sqrt(Math.pow(fresh.x-old.x,2)+Math.pow(fresh.y-old.y,2)+Math.pow(fresh.z-old.z,2)));
                    }
                    if (row.role === 'fixture-peer') { packetRate = rate(row.result.id,''); positionRate = rate(row.result.id,'globalPosition'); simulationRate = rate(row.result.id,'',true); }
                } catch (error) { /* Native read failure is unknown, never raw error text. */ }
                var state = signalState();
                print({ version:1, kind:'sample', at:now(), sequence:sequence, role:row.role,
                    batchMs:batchMs, publishedPoseAgeMs:number(publicationAt-row.poseAt), avatarBuildMs:number(row.completedAt-row.started),
                    jointNamesMs:row.names, jointRotationsMs:row.rotations, jointTranslationsMs:row.translations,
                    postPublicationPoseDeltaMeters:distance, postPublicationProbeMs:passive?null:elapsed(probeStarted),
                    peerPacketRateHz:packetRate, peerGlobalPositionUpdateRateHz:positionRate, peerSimulationRateHz:simulationRate,
                    capturedFixtureTargetDistanceMeters:capturedFixtureTargetDistance(row),
                    nativeDelivery: typeof config.delivery === 'function' ? config.delivery() : null, gatewayDelivery:null,
                    interstitialState:state.interstitialState, interstitialSignalAgeMs:state.interstitialSignalAgeMs });
            });
        },
        authorObservation: function () {
            if (!current()) return;
            var state = signalState();
            print({version:1,kind:'author-transmission',at:now(),interstitialState:state.interstitialState,
                interstitialSignalAgeMs:state.interstitialSignalAgeMs,
                cachedMyAvatarSendRateHz:passive?null:stats('myAvatarSendRate'),cachedAvatarMixerOutPps:passive?null:stats('avatarMixerOutPps'),
                authorGlobalPositionOutboundKbps:passive?null:authorRate('globalPositionOutbound'),
                authorLocalPositionOutboundKbps:passive?null:authorRate('localPositionOutbound'),
                statsFreshness:'not-forced-or-established'});
        },
        stop: stop
    };
}
