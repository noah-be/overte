// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Standalone --testScript. The private host runner prepends a fresh run ID and
// two independent challenges. Both captures come from the actual device input.
(function () {
    "use strict";
    var report = { schemaVersion: 1, runId: OVERTE_ACOUSTIC_RUN.id,
        buildVersion: String(About.buildVersion), startedEpochMs: Date.now(),
        ok: false, captures: [], cleanup: { restored: false } };
    var original = null, localEcho = false, serverEcho = false;
    var timer = null, watchdog = null, phase = "permission", sequence = 0;
    var readySince = 0, revision = null, phaseStarted = Date.now(), lastStatus = null;
    var keys = ["muted", "pushToTalk", "noiseReduction", "acousticEchoCancellation",
        "avatarGain", "serverInjectorGain", "localInjectorGain", "systemInjectorGain"];
    function native(action, fields) {
        var command = { schemaVersion: 1, commandId: report.runId + "-" + (++sequence), action: action };
        Object.keys(fields || {}).forEach(function (key) { command[key] = fields[key]; });
        var result = Test.acousticTest(command);
        if (!result || !result.ok) { throw new Error(result && result.error || "acoustic-native-failed"); }
        if (result.sourceEnabled || result.sourceClockActive) { throw new Error("acoustic-synthetic-input-active"); }
        return result;
    }
    function restore() {
        if (timer !== null) { Script.clearInterval(timer); timer = null; }
        if (watchdog !== null) { Script.clearTimeout(watchdog); watchdog = null; }
        var reset = false, settings = true;
        try {
            var restored = native("reset");
            reset = restored.prepared === false && restored.measurementMode === false;
        } catch (error) { reset = false; }
        if (original) {
            try {
                keys.forEach(function (key) { Audio[key] = original[key]; });
                Audio.setLocalEcho(localEcho);
                Audio.setServerEcho(serverEcho);
                keys.forEach(function (key) { if (Audio[key] !== original[key]) { settings = false; } });
                settings = settings && Boolean(Audio.getLocalEcho()) === localEcho
                    && Boolean(Audio.getServerEcho()) === serverEcho;
            } catch (error) { settings = false; }
        }
        report.cleanup = { restored: reset && settings, nativeReset: reset, audioSettingsRestored: settings };
    }
    function finish(error) {
        if (phase === "finished") { return; }
        phase = "finished";
        if (error) { report.error = String(error); }
        restore();
        report.ok = !error && report.captures.length === 2 && report.cleanup.restored;
        report.completedEpochMs = Date.now();
        Test.saveObject(report, "acoustic-result.json");
        // Raw captures are a short-lived private transport, not retained lab
        // artifacts. Keep only the receipt on-device after the host pulls them.
        Script.setTimeout(function () {
            report.captures.forEach(function (capture) { delete capture.wavBase64; });
            report.capturePayloadExpired = true;
            Test.saveObject(report, "acoustic-result.json");
            Script.stop();
        }, 45000);
    }
    function stableReady(status) {
        if (!status.iosForeground || status.iosInterrupted || !status.iosCaptureAllowed ||
                !status.builtInMicrophone || !status.builtInSpeaker || !status.inputPresent ||
                status.inputState !== 0 || status.inputError !== 0) {
            readySince = 0;
            return false;
        }
        if (!readySince || revision !== status.outputRevision) {
            revision = status.outputRevision;
            readySince = Date.now();
        }
        return readySince && Date.now() - readySince >= 1200;
    }
    function beginCapture(kind) {
        var challenge = kind === "control" ? OVERTE_ACOUSTIC_RUN.control : OVERTE_ACOUSTIC_RUN.signal;
        native("capture-start", { seconds: 8, challenge: challenge });
        phase = kind;
        phaseStarted = Date.now();
    }
    function tick() {
        try {
            // A loaded file-backed serverless scene reports isConnected=true.
            // Its file protocol, together with the native domain-server guard,
            // keeps this physical test independent of an online audio mixer.
            if (String(location.protocol) !== "file") {
                throw new Error("acoustic-test-requires-local-world");
            }
            var status = native("status");
            lastStatus = status;
            if (phase === "permission") {
                // A system permission alert resigns UIKit foreground. No audio
                // settings, capture or playback proceed until it is answered.
                if (status.iosPermission === 0 || !status.iosForeground) { return; }
                if (status.iosPermission !== 1) { throw new Error("acoustic-microphone-permission-denied"); }
                original = {};
                keys.forEach(function (key) { original[key] = Audio[key]; });
                localEcho = Boolean(Audio.getLocalEcho());
                serverEcho = Boolean(Audio.getServerEcho());
                Audio.setLocalEcho(false);
                Audio.setServerEcho(false);
                Audio.pushToTalk = false;
                Audio.noiseReduction = false;
                Audio.acousticEchoCancellation = false;
                Audio.avatarGain = -96;
                Audio.serverInjectorGain = -96;
                Audio.localInjectorGain = -96;
                // The local, non-spatial challenge uses the system sound bus.
                Audio.systemInjectorGain = 0;
                Audio.muted = false;
                phase = "native-ready";
                phaseStarted = Date.now();
                return;
            }
            if (!status.iosForeground || status.iosInterrupted || status.iosPermission !== 1) {
                throw new Error("acoustic-permission-or-lifecycle-changed");
            }
            if (phase === "native-ready") {
                if (stableReady(status)) {
                    native("prepare");
                    phase = "measurement-ready";
                    readySince = 0;
                    revision = null;
                    phaseStarted = Date.now();
                } else if (Date.now() - phaseStarted > 10000) {
                    throw new Error("acoustic-built-in-input-unavailable");
                }
                return;
            }
            if (!status.prepared || !status.measurementMode || !status.builtInMicrophone || !status.builtInSpeaker) {
                throw new Error("acoustic-route-or-mode-changed");
            }
            if (phase === "measurement-ready") {
                if (stableReady(status)) { beginCapture("control"); }
                else if (Date.now() - phaseStarted > 10000) { throw new Error("acoustic-measurement-input-unavailable"); }
                return;
            }
            if (status.captureInvalid) { throw new Error("acoustic-capture-invalidated"); }
            if (phase === "playback" && !report.playbackStarted && Date.now() - phaseStarted >= 800) {
                if (status.physicalInputCallbacks < 1) { throw new Error("acoustic-no-physical-input"); }
                var played = native("play", { challenge: OVERTE_ACOUSTIC_RUN.signal });
                if (!played.playing) { throw new Error("acoustic-output-not-playing"); }
                report.playbackStarted = true;
            }
            if (status.captureComplete) {
                var captured = native("capture-stop");
                captured.kind = phase;
                report.captures.push(captured);
                if (phase === "control") { beginCapture("playback"); }
                else { finish(); }
            } else if (Date.now() - phaseStarted > 10000) { throw new Error("acoustic-capture-timeout"); }
        } catch (error) {
            report.lastNativeStatus = lastStatus;
            finish(error.message || "acoustic-script-failed");
        }
    }
    if (!/^[a-z0-9-]{1,80}$/.test(report.runId) || !/^[0-9a-f]{32}$/.test(OVERTE_ACOUSTIC_RUN.control) ||
            !/^[0-9a-f]{32}$/.test(OVERTE_ACOUSTIC_RUN.signal) || OVERTE_ACOUSTIC_RUN.control === OVERTE_ACOUSTIC_RUN.signal) {
        report.error = "acoustic-invalid-run";
        Test.saveObject(report, "acoustic-result.json");
        return;
    }
    if (typeof Test.acousticTest !== "function") {
        report.error = "acoustic-test-build-required";
        Test.saveObject(report, "acoustic-result.json");
        return;
    }
    Script.scriptEnding.connect(restore);
    // Permission presentation gets its own bounded wait. No automatic reset,
    // dismissal or acceptance is performed inside the product script.
    watchdog = Script.setTimeout(function () { finish("acoustic-watchdog-expired"); }, 120000);
    timer = Script.setInterval(tick, 200);
}());
