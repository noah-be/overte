import QtQuick 2.7
import "../../../controlsUit" as HifiControls

HifiControls.TouchUiMetrics {
    readonly property bool showScriptingPlugins: profile.scriptingPluginsAvailable
    readonly property int titleHeight: directTouch ? 44 : 60
    readonly property int headerHeight: directTouch ? 40 : 55
    readonly property int rowHeight: directTouch ? 56 : 80
    readonly property int buttonHeight: directTouch ? 44 : 40
}
