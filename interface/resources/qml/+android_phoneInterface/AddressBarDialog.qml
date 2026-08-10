// Phone-only screen-space destination dialog. The existing tablet address UI
// assumes a system tablet and HMD focus entity, neither of which exists here.
import Hifi 1.0
import QtQuick 2.7
import controlsUit 1.0 as HifiControls

FocusScope {
    id: root
    objectName: "AddressBarDialog"
    property bool shown: true
    readonly property int maximumAddressLength: 4096
    visible: shown
    anchors.fill: parent

    function closeDialog() {
        Qt.inputMethod.hide()
        DialogsManager.hideAddressBar()
    }

    function goToAddress() {
        var candidate = addressField.text.trim()
        if (candidate.length === 0 || candidate.length > maximumAddressLength ||
                /[\u0000-\u001f\u007f]/.test(candidate)) {
            addressError.text = qsTr("Enter a valid address.")
            addressField.forceActiveFocus()
            return
        }
        addressError.text = ""
        addressDialog.loadAddress(candidate)
        closeDialog()
    }

    Rectangle {
        anchors.fill: parent
        color: "#b0000000"

        MouseArea {
            anchors.fill: parent
            Accessible.ignored: true
            onClicked: root.closeDialog()
        }
    }

    Rectangle {
        id: panel
        width: Math.min(parent.width - 48, 720)
        height: content.implicitHeight + 48
        anchors.centerIn: parent
        radius: 18
        color: "#e6282d33"
        border.color: "#6679858e"

        MouseArea {
            anchors.fill: parent
            Accessible.ignored: true
            onClicked: mouse.accepted = true
        }

        Column {
            id: content
            width: parent.width - 48
            anchors.centerIn: parent
            spacing: 18

            Text {
                width: parent.width
                text: qsTr("Go to a place, user, path, or network address")
                color: "white"
                font.pixelSize: 24
                font.bold: true
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
            }

            HifiControls.TextField {
                id: addressField
                objectName: "PhoneAddressField"
                width: parent.width
                height: 52
                placeholderText: qsTr("Address")
                maximumLength: root.maximumAddressLength
                activeFocusOnPress: true
                activeFocusOnTab: true
                Accessible.role: Accessible.EditableText
                Accessible.name: qsTr("Destination address")
                Accessible.description: qsTr("Place, user, path, or network address")
                font.pixelSize: 20
                Keys.onReturnPressed: root.goToAddress()
            }

            Text {
                id: addressError
                objectName: "PhoneAddressError"
                width: parent.width
                visible: text.length > 0
                color: "#ff7777"
                font.pixelSize: 18
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12

                HifiControls.Button {
                    objectName: "PhoneAddressBackButton"
                    width: Math.min(140, (content.width - 36) / 4)
                    text: qsTr("Back")
                    enabled: addressDialog.backEnabled
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: qsTr("Go to the previous destination")
                    androidClickAction: function () { addressDialog.loadBack(); root.closeDialog() }
                }
                HifiControls.Button {
                    objectName: "PhoneAddressHomeButton"
                    width: Math.min(140, (content.width - 36) / 4)
                    text: qsTr("Home")
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: qsTr("Go to the home destination")
                    androidClickAction: function () { addressDialog.loadHome(); root.closeDialog() }
                }
                HifiControls.Button {
                    objectName: "PhoneAddressGoButton"
                    width: Math.min(140, (content.width - 36) / 4)
                    text: qsTr("Go")
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: qsTr("Open the entered destination")
                    androidClickAction: function () { root.goToAddress() }
                }
                HifiControls.Button {
                    objectName: "PhoneAddressCancelButton"
                    width: Math.min(140, (content.width - 36) / 4)
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: qsTr("Close without changing destination")
                    androidClickAction: function () { root.closeDialog() }
                }
            }
        }
    }

    AddressBarDialog {
        id: addressDialog
        anchors.fill: parent
        z: -1
        onHostChanged: root.closeDialog()
    }

    onShownChanged: {
        addressDialog.observeShownChanged(shown)
        if (shown) {
            addressError.text = ""
            addressField.text = AddressManager.href
            addressField.selectAll()
            addressField.forceActiveFocus()
        } else {
            Qt.inputMethod.hide()
        }
    }

    Component.onCompleted: {
        addressDialog.observeShownChanged(shown)
        addressError.text = ""
        addressField.text = AddressManager.href
        addressField.selectAll()
        addressField.forceActiveFocus()
    }

    Component.onDestruction: {
        addressField.focus = false
        Qt.inputMethod.hide()
    }
}
