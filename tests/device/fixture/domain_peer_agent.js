// Deterministic avatar assignment used only by the ephemeral E2E domain.
(function () {
    "use strict";

    var elapsed = 0.0;
    var origin = { x: 2.0, y: 0.0, z: 2.0 };
    Agent.isListeningToAudioStream = false;
    Agent.isAvatar = true;
    Avatar.displayName = "OVERTE_E2E_PEER";
    Avatar.position = origin;

    function update(deltaTime) {
        elapsed += Number(deltaTime);
        Avatar.position = {
            x: origin.x + 0.75 * Math.sin(elapsed),
            y: origin.y,
            z: origin.z
        };
    }

    Script.update.connect(update);
    Script.scriptEnding.connect(function () {
        Script.update.disconnect(update);
        Agent.isAvatar = false;
    });
}());
