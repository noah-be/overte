// PC voice-lab client. VOICE_PEER_CONFIG is prepended by the local controller.
// Commands and snapshots use a loopback-only authenticated channel.
(function () {
    "use strict";
    var config = VOICE_PEER_CONFIG;
    var sequence = 0;
    var lastCommand = "";
    var mixerReady = false;
    var peak = 0;
    var busy = false;
    var commandError = "";
    MyAvatar.displayName = "OVERTE_VOICE_TEST_PC";
    Audio.muted = true;
    Audio.pushToTalk = false;
    Audio.noiseReduction = false;
    Audio.acousticEchoCancellation = false;
    Audio.avatarGain = 0;
    Audio.serverInjectorGain = -96;
    Audio.localInjectorGain = -96;
    Audio.systemInjectorGain = -96;
    Audio.setLocalEcho(false);
    Audio.setServerEcho(false);
    Audio.receivedFirstPacket.connect(function () { mixerReady = true; });
    Audio.disconnected.connect(function () { mixerReady = false; });
    Audio.inputLevelChanged.connect(function (level) { peak = Math.max(peak, Number(level)); });

    function request(method, path, data, done) {
        var xhr = new XMLHttpRequest();
        xhr.open(method, config.url + path, true);
        xhr.setRequestHeader("Authorization", "Bearer " + config.token);
        xhr.timeout = 2000;
        xhr.onreadystatechange = function () {
            if (xhr.readyState === 4) {
                if (done) { done(xhr.status, xhr.responseText); }
            }
        };
        xhr.send(data === null ? null : JSON.stringify(data));
    }

    function tick() {
        sequence += 1;
        request("POST", "/snapshot", {
            session: config.session, sequence: sequence, commandId: lastCommand,
            commandError: commandError, mixerReady: mixerReady,
            connected: Boolean(location.isConnected), domainId: String(location.domainID),
            muted: Boolean(Audio.muted), localEcho: Boolean(Audio.getLocalEcho()),
            serverEcho: Boolean(Audio.getServerEcho()), inputPeak: peak,
            position: { x: MyAvatar.position.x, y: MyAvatar.position.y, z: MyAvatar.position.z },
            build: { version: String(About.buildVersion), date: String(About.buildDate) }
        }, null);
        peak = Number(Audio.inputLevel);
        if (busy) { return; }
        busy = true;
        request("GET", "/command", null, function (status, body) {
            busy = false;
            if (status !== 200) { return; }
            try {
                var command = JSON.parse(body);
                if (!command.id || command.id === lastCommand) { return; }
                if (typeof command.muted !== "boolean" || typeof command.localEcho !== "boolean"
                        || typeof command.serverEcho !== "boolean") { return; }
                Audio.muted = command.muted;
                Audio.setLocalEcho(command.localEcho);
                Audio.setServerEcho(command.serverEcho);
                if (command.position) { MyAvatar.position = command.position; }
                commandError = "";
                lastCommand = command.id;
            } catch (error) {
                commandError = "voice-command-failed";
            }
        });
    }
    var timer = Script.setInterval(tick, 250);
    Script.scriptEnding.connect(function () {
        Script.clearInterval(timer);
        Audio.muted = true;
        Audio.setLocalEcho(false);
        Audio.setServerEcho(false);
    });
}());
