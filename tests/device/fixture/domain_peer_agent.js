// Deterministic avatar assignment used only by the ephemeral E2E domain.
(function () {
    "use strict";

    var elapsed = 0.0;
    var updateCount = 0;
    var lastReport = 0.0;
    var origin = { x: 2.0, y: 0.0, z: 2.0 };
    Agent.isListeningToAudioStream = false;
    Agent.isAvatar = true;
    Avatar.displayName = "OVERTE_E2E_PEER";
    Avatar.position = origin;

    function update(deltaTime) {
        elapsed += Number(deltaTime);
        updateCount += 1;
        Avatar.position = {
            x: origin.x + 0.75 * Math.sin(elapsed),
            y: origin.y,
            z: origin.z
        };
        if (elapsed - lastReport >= 1.0) {
            lastReport = elapsed;
            // Assignment scripts can start before the avatar mixer's socket
            // becomes active. The released agent clears its initial identity
            // update even when there is no connected mixer, so publish the
            // fixture's fixed name again through the real avatar API.
            Avatar.displayName = "OVERTE_E2E_PEER";
            var request = new XMLHttpRequest();
            request.open("POST", Script.resolvePath("peer-state"), true);
            request.setRequestHeader("Content-Type", "application/json");
            request.send(JSON.stringify({schemaVersion: 1, avatarEnabled: Boolean(Agent.isAvatar),
                displayName: String(Avatar.displayName), updates: updateCount}));
        }
    }

    Script.update.connect(update);
    Script.scriptEnding.connect(function () {
        Script.update.disconnect(update);
        Agent.isAvatar = false;
    });
}());
