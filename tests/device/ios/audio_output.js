// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
/* Physical output PCM at system volume zero; no acoustic microphone capture. */
(function () {
    "use strict";
    var run = OVERTE_OUTPUT_RUN;
    var report = { schemaVersion: 1, runId: run.id, buildVersion: String(About.buildVersion),
        startedEpochMs: Date.now(), captures: [], cleanup: { restored: false } };
    var keys = ["muted", "pushToTalk", "avatarGain", "serverInjectorGain", "localInjectorGain", "systemInjectorGain"];
    var original = null, localEcho = false, serverEcho = false, timer = null, watchdog = null;
    var injector = null, step = -1, phase = "ready", since = Date.now(), sequence = 0;
    var sounds = [];
    function command(action, fields) {
        var request = { schemaVersion: 1, commandId: run.id + "-" + (++sequence), action: action };
        Object.keys(fields || {}).forEach(function (key) { request[key] = fields[key]; });
        var result = Test.voiceTest(request);
        if (!result || !result.ok) { throw new Error("output-native-capture-failed"); }
        return result;
    }
    function status() {
        var value = Test.acousticTest({ schemaVersion: 1, commandId: run.id + "-status", action: "status" });
        if (!value.ok || value.sourceEnabled || value.sourceClockActive || value.prepared || value.measurementMode) {
            throw new Error("output-unexpected-test-state");
        }
        return value;
    }
    function cleanup() {
        if (timer !== null) { Script.clearInterval(timer); timer = null; }
        if (watchdog !== null) { Script.clearTimeout(watchdog); watchdog = null; }
        if (injector) { injector.stop(); injector = null; }
        var restored = true;
        try {
            command("reset");
            if (original) {
                keys.forEach(function (key) { Audio[key] = original[key]; });
                Audio.setLocalEcho(localEcho);
                Audio.setServerEcho(serverEcho);
                keys.forEach(function (key) { restored = restored && Audio[key] === original[key]; });
                restored = restored && Boolean(Audio.getLocalEcho()) === localEcho
                    && Boolean(Audio.getServerEcho()) === serverEcho;
            }
        } catch (error) { restored = false; }
        report.cleanup.restored = restored;
    }
    function finish(error) {
        if (phase === "finished") { return; }
        phase = "finished";
        if (error) { report.error = String(error); }
        cleanup();
        report.ok = !error && report.cleanup.restored && report.captures.length === 4;
        report.completedEpochMs = Date.now();
        Test.saveObject(report, "output-playback-result.json");
        Script.setTimeout(function () {
            report.captures.forEach(function (capture) { delete capture.wavBase64; });
            report.capturePayloadExpired = true;
            Test.saveObject(report, "output-playback-result.json");
            Script.stop();
        }, 45000);
    }
    function tick() {
        try {
            var value = status();
            if (String(location.protocol) !== "file") { throw new Error("output-requires-local-world"); }
            if (!value.iosForeground) { return; }
            if (value.iosPermission !== run.permission) { throw new Error("output-unexpected-permission"); }
            if (step === -1) {
                if (!sounds.every(function (sound) { return sound.downloaded; })) { return; }
                original = {};
                keys.forEach(function (key) { original[key] = Audio[key]; });
                localEcho = Boolean(Audio.getLocalEcho());
                serverEcho = Boolean(Audio.getServerEcho());
                Audio.setLocalEcho(false);
                Audio.setServerEcho(false);
                Audio.pushToTalk = false;
                Audio.avatarGain = -96;
                Audio.serverInjectorGain = -96;
                Audio.localInjectorGain = -96;
                Audio.systemInjectorGain = 0;
                Audio.muted = false;
                step = 0;
                since = Date.now();
                return;
            }
            var muted = step === 2, expected = muted ? 3 : (run.permission === 1 ? 2 : 1);
            var captureAllowed = run.permission === 1 && !muted;
            var ready = value.iosOutcome === expected && value.nativeMuted === muted
                && value.iosCaptureAllowed === captureAllowed && value.inputPresent === captureAllowed
                && (!captureAllowed || (value.inputState === 0 && value.inputError === 0))
                && !value.iosInterrupted && value.builtInSpeaker && value.physicalDevice;
            if (!ready) {
                if (phase === "capture" || Date.now() - since > 10000) {
                    throw new Error("output-native-state-invalid");
                }
                return;
            }
            if (value.outputVolume !== 0) { throw new Error("output-system-volume-not-zero"); }
            if (phase === "ready" && Date.now() - since >= 3000) {
                command("capture-start", { seconds: 8 });
                phase = "capture";
                since = Date.now();
                return;
            }
            if (phase === "capture") {
                if (step !== 0 && Date.now() - since >= 800 && !injector) {
                    injector = Audio.playSound(sounds[step - 1], { localOnly: true, volume: 1 });
                    if (!injector) { throw new Error("output-local-injector-unavailable"); }
                }
                if (Date.now() - since >= 8400) {
                    var capture = command("capture-stop");
                    capture.phase = ["quiet-control", "unmuted", "muted", "unmuted-again"][step];
                    capture.challenge = run.challenges[Math.max(0, step - 1)];
                    capture.status = value;
                    report.captures.push(capture);
                    if (injector) { injector.stop(); injector = null; }
                    if (step === 3) { finish(); return; }
                    step++;
                    Audio.muted = step === 2;
                    phase = "ready";
                    since = Date.now();
                }
            }
        } catch (error) { finish(error.message || "output-script-failed"); }
    }
    if (!/^[a-z0-9-]{1,80}$/.test(run.id) || !Array.isArray(run.challenges) || run.challenges.length !== 3
            || !run.challenges.every(function (nonce) { return /^[0-9a-f]{32}$/.test(nonce); })
            || run.challenges[0] === run.challenges[1] || run.challenges[0] === run.challenges[2]
            || run.challenges[1] === run.challenges[2] || (run.permission !== 1 && run.permission !== 2)
            || !Array.isArray(run.urls) || run.urls.length !== 3) {
        report.error = "output-invalid-run";
        Test.saveObject(report, "output-playback-result.json");
        return;
    }
    if (typeof Test.voiceTest !== "function" || typeof Test.acousticTest !== "function") {
        report.error = "output-test-build-required";
        Test.saveObject(report, "output-playback-result.json");
        return;
    }
    sounds = run.urls.map(function (url) { return SoundCache.getSound(url); });
    Script.scriptEnding.connect(cleanup);
    watchdog = Script.setTimeout(function () { finish("output-playback-timeout"); }, 75000);
    timer = Script.setInterval(tick, 100);
}());
