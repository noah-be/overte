import QtQuick 2.15
import controlsUit 1.0 as HifiControls

HifiControls.TouchUiMetrics {
    readonly property real contentScale: 1.0
    readonly property bool showGraphicsSettings: profile.graphicsSettingsAvailable
    readonly property bool showControllerSettings: profile.controllerSettingsAvailable
    readonly property bool showPicoResolutionSettings: profile.picoResolutionSettingsAvailable
}
