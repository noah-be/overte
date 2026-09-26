// QAction owns checked state; triggered() dispatches through the native bridge.
import QtQuick.Controls 2.3

MenuItem {
    readonly property int type: 1
    property bool tabletVisible: true
    property bool tabletExclusive: false
    property string tabletShortcut: ""
    function trigger() {
        if (enabled && tabletVisible) {
            triggered()
        }
    }
}
