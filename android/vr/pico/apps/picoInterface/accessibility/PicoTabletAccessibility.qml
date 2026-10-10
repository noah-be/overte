// A real rendered HUD control, also exposed to Android accessibility services.
import QtQuick 2.7
import controlsUit 1.0 as Uit

Uit.Button {
    property bool tabletOpen: false
    objectName: tabletOpen ? "tablet.close" : "tablet.open"
    Accessible.role: Accessible.Button
    Accessible.name: text
    text: tabletOpen ? qsTr("Close tablet") : qsTr("Open tablet")
    width: 240
    height: 64
    z: 90000
    x: parent ? Math.max(0, parent.width - width - 24) : 0
    y: parent ? Math.max(0, parent.height - height - 24) : 0
    androidClickAction: function () {
        if (tabletOpen) { HMD.closeTablet(); }
        else { HMD.openTablet(); }
    }
}
