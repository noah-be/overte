import QtQuick 2.7
import QtQuick.Controls 2.3
import controlsUit 1.0 as HifiControls

// One navigation surface for every direct-touch, screen-space tablet host.
Item {
    id: navigation
    property bool backVisible: true
    property real contentScale: 1
    signal backRequested()
    signal homeRequested()
    signal closeRequested()
    HifiControls.TouchUiMetrics {
        id: metrics
        availableWidth: navigation.width / navigation.contentScale
    }
    implicitHeight: Math.max(48, Math.ceil(48 * metrics.textScale)) * contentScale
    height: visible ? implicitHeight : 0

    Row {
        anchors.centerIn: parent
        spacing: 12
        scale: navigation.contentScale
        Repeater {
            model: [
                { key: "back", label: qsTr("Back"), accessible: qsTr("Go back") },
                { key: "home", label: qsTr("Home"), accessible: qsTr("Tablet home") },
                { key: "close", label: qsTr("Close"), accessible: qsTr("Close tablet") }
            ]
            delegate: HifiControls.Button {
                objectName: "nav." + modelData.key
                visible: modelData.key !== "back" || navigation.backVisible
                width: Math.max(48, Math.min(112,
                    (navigation.width / navigation.contentScale - 40) / 3))
                height: navigation.implicitHeight / navigation.contentScale
                text: modelData.label
                font.pixelSize: Math.round(16 * metrics.textScale)
                Accessible.name: modelData.accessible
                androidClickAction: activate
                onClicked: { if (!usesAndroidClickAction) { activate() } }
                function activate() {
                    if (modelData.key === "back") { navigation.backRequested() }
                    else if (modelData.key === "home") { navigation.homeRequested() }
                    else { navigation.closeRequested() }
                }
            }
        }
    }
}
