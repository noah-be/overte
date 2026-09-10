import QtQuick 2.7

QtObject {
    // The Phone package has no complete user-managed scripting-plugin flow.
    readonly property bool showScriptingPlugins: false
    // WindowRoot supplies the physical 250% scale; keep logical layouts compact
    // enough for the reduced viewport left while the Android IME is visible.
    readonly property int titleHeight: 44
    readonly property int headerHeight: 40
    readonly property int rowHeight: 56
    readonly property int buttonHeight: 44
}
