import QtQuick 2.15
import controlsUit 1.0 as HifiControls

HifiControls.TouchUiMetrics {
    readonly property real contentScale: 1.0
    readonly property bool showGraphicsSettings: profile.graphicsSettingsAvailable
    readonly property bool showControllerSettings: profile.controllerSettingsAvailable
    readonly property bool showPicoResolutionSettings: profile.picoResolutionSettingsAvailable
    // Product-specific pages fail closed unless an immutable QFileSelector
    // profile for the compiled Android target explicitly enables them.
    readonly property bool showPicoInteractionSettings: false
}
