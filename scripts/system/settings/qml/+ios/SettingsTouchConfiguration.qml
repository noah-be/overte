import QtQuick 2.15
import controlsUit 1.0 as HifiControls

// iOS is also selected through the Android phone interface compatibility
// path, but Settings needs the adaptive dimensions exposed by the shared
// touch metrics object.  This higher-priority selector keeps the bounded
// iOS feature profile while restoring those dimensions.
HifiControls.TouchUiMetrics {
    readonly property real contentScale: 1.0
    readonly property bool showGraphicsSettings: profile.graphicsSettingsAvailable
    readonly property bool showControllerSettings: profile.controllerSettingsAvailable
    readonly property bool showPicoResolutionSettings: profile.picoResolutionSettingsAvailable
    Component.onCompleted: console.log(
        "OVERTE_IOS_TOUCH_UI_GATE stage=settings-ios-selector-ready")
}
