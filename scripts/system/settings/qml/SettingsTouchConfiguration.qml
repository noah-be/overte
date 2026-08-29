import QtQuick 2.15
import controlsUit 1.0 as HifiControls

HifiControls.TouchUiMetrics {
    readonly property real contentScale: 1.0
    readonly property bool showGraphicsSettings: profile.graphicsSettingsAvailable
    readonly property bool showControllerSettings: profile.controllerSettingsAvailable
    readonly property bool showVrRenderResolutionSettings: profile.vrRenderResolutionAvailable
    // Compatibility projection for existing selector-backed Settings QML.
    readonly property bool showPicoResolutionSettings: profile.picoResolutionSettingsAvailable
    // Product-specific pages fail closed unless an immutable QFileSelector
    // profile for the compiled Android target explicitly enables them.
    readonly property bool showPicoInteractionSettings: false

    function admitsSemanticControl(controlId) {
        if (controlId === "settings.general" || controlId === "settings.audio"
                || controlId === "settings.security") {
            return true
        }
        if (controlId === "settings.graphics") {
            return showGraphicsSettings
        }
        if (controlId === "settings.controllers") {
            return showControllerSettings
        }
        return false
    }
}
