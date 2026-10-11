// Deterministic avatar assignment used only by the ephemeral E2E domain.
(function () {
    "use strict";

    var elapsed = 0.0;
    var updates = 0;
    var origin = { x: 2.0, y: 0.0, z: 2.0 };
    Agent.isListeningToAudioStream = false;
    Agent.isAvatar = true;
    Avatar.displayName = "OVERTE_E2E_PEER";
    Avatar.position = origin;

    function update(deltaTime) {
        updates += 1;
        elapsed += Number(deltaTime);
        Avatar.position = {
            x: origin.x + 0.75 * Math.sin(elapsed),
            y: origin.y,
            z: origin.z
        };
    }

    function reportState() {
        // The first identity packet can precede the active mixer socket. Keep
        // the real agent identity announced after connection and reconnection;
        // receivers must still independently observe this avatar and movement.
        Avatar.displayName = "OVERTE_E2E_PEER";
        var request = new XMLHttpRequest();
        request.open("POST", Script.resolvePath("peer-state"), true);
        request.setRequestHeader("Content-Type", "application/json");
        request.send(JSON.stringify({ schemaVersion: 1,
            avatarEnabled: Boolean(Agent.isAvatar),
            displayName: String(Avatar.displayName), updates: updates }));
    }

    var reportTimer = Script.setInterval(reportState, 1000);
    Script.update.connect(update);
    Script.scriptEnding.connect(function () {
        Script.clearInterval(reportTimer);
        Script.update.disconnect(update);
        Agent.isAvatar = false;
    });
}());
