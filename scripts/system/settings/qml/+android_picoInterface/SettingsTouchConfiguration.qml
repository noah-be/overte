import QtQuick 2.15
import controlsUit 1.0 as HifiControls

HifiControls.TouchUiMetrics {
    // This selector is derived from the compiled HIFI_ANDROID_APP target and
    // cannot be changed through persisted Settings values.
    readonly property real contentScale: 1.0
    readonly property bool showGraphicsSettings: true
    readonly property bool showControllerSettings: true
    readonly property bool showPicoResolutionSettings: true
    readonly property bool showPicoInteractionSettings: true

    function admitsSemanticControl(controlId) {
        return controlId === "settings.general" || controlId === "settings.audio"
            || controlId === "settings.security" || controlId === "settings.graphics"
            || controlId === "settings.controllers"
    }
}
