// Android phone additions to the tablet General Settings categories.

import QtQuick 2.7
import QtQuick.Controls 2.2
import "../tabletWindows"
import "../../dialogs"

StackView {
    id: profileRoot
    PhoneGeneralPreferencesPolicy { id: phonePolicy }
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
        // Keep this fail-closed. The shared User Interface category still
        // contains desktop toolbar/tablet and VR laser/keyboard controls;
        // Snapshots exposes a desktop directory picker; HMD and Plugins are
        // VR-only. Privacy includes crash reporting and Discord controls that
        // are compiled as no-ops in the phone target. Hidden individual
        // preferences are still loaded and saved by TabletPreferencesDialog,
        // so only admit categories whose complete contract is meaningful.
        showCategories: phonePolicy.allowedCategories
    }
}
