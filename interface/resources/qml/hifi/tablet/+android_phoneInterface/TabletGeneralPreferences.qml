// Android phone additions to the tablet General Settings categories.

import QtQuick 2.7
import QtQuick.Controls 2.2
import "../tabletWindows"
import "../../dialogs"

StackView {
    id: profileRoot
    initialItem: root
    objectName: "stack"
    property string title: "General Settings"
    property alias gotoPreviousApp: root.gotoPreviousApp
    property alias gotoPreviousAppFromScript: root.gotoPreviousAppFromScript
    signal sendToScript(var message)

    function pushSource(path) {
        var item = Qt.createComponent(Qt.resolvedUrl(path));
        profileRoot.push(item);
    }

    function popSource() {
        profileRoot.pop();
    }

    function emitSendToScript(message) {
        profileRoot.sendToScript(message);
    }

    TabletPreferencesDialog {
        id: root
        objectName: "TabletGeneralPreferences"
        showCategories: ["Navigation", "User Interface", "Mouse Sensitivity", "HMD", "Snapshots", "Privacy", "Plugins"]
    }
}
