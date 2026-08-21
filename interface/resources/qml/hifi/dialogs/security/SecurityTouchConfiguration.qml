import QtQuick 2.7
import "../../../controlsUit" as HifiControls

HifiControls.TouchUiMetrics {
    readonly property bool showScriptingPlugins: profile.scriptingPluginsAvailable
    readonly property int titleHeight: directTouch
        ? Math.max(44, Math.ceil(32 * textScale)) : 60
    readonly property int headerHeight: directTouch
        ? Math.max(40, Math.ceil(28 * textScale)) : 55
    readonly property int rowHeight: directTouch
        ? Math.max(56, Math.ceil(40 * textScale)) : 80
    readonly property int buttonHeight: directTouch
        ? Math.max(44, adaptiveMinimumControlHeight,
            Math.ceil(28 * textScale)) : 40
}
