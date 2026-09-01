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

    HifiControls.TouchUiMetrics {
        id: touchMetrics
        availableWidth: root.width
        availableHeight: root.height
    }

    function closeDialog() {
        Qt.inputMethod.hide()
        DialogsManager.hideAddressBar()
    }

    function goToAddress() {
        var candidate = addressField.text.trim()
        if (candidate.length === 0 || candidate.length > maximumAddressLength ||
                /[\u0000-\u001f\u007f]/.test(candidate)) {
            addressError.text = qsTr("Enter a valid address.")
            requestAddressInput()
            return
        }
        addressError.text = ""
        addressDialog.loadAddress(candidate)
        closeDialog()
    }

    function requestAddressInput() {
        if (!addressField.activeFocus) {
            addressField.forceActiveFocus()
            return
        }
        Qt.callLater(function () {
            if (root.shown && addressField.activeFocus) {
                DialogsManager.requestPhoneSoftwareKeyboard()
                touchMetrics.ensureVisible(viewport, addressField)
            }
        })
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

    Flickable {
        id: viewport
        anchors.fill: parent
        contentWidth: width
        contentHeight: Math.max(height,
            panel.y + panel.height + touchMetrics.spacingLarge)
        clip: true
        boundsBehavior: touchMetrics.directTouch
            ? Flickable.DragOverBounds : Flickable.StopAtBounds
        pressDelay: touchMetrics.pressDelay
        flickDeceleration: touchMetrics.flickDeceleration
        maximumFlickVelocity: touchMetrics.maximumFlickVelocity

    Rectangle {
        id: panel
        objectName: "PhoneAddressPanel"
        width: Math.max(1,
            Math.min(viewport.width - 2 * touchMetrics.spacingLarge, 720))
        height: content.implicitHeight + 48
        x: Math.max(touchMetrics.spacingLarge, (viewport.width - width) / 2)
        y: touchMetrics.keyboardVisible
            ? Math.max(touchMetrics.safeInsetTop + touchMetrics.spacingLarge,
                touchMetrics.spacingLarge)
            : Math.max(touchMetrics.spacingLarge, (viewport.height - height) / 2)
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
                font.pixelSize: Math.round(24 * touchMetrics.textScale)
                font.bold: true
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
            }

            HifiControls.TextField {
                id: addressField
                objectName: "PhoneAddressField"
                width: parent.width
                height: Math.max(52, implicitHeight)
                placeholderText: qsTr("Address")
                maximumLength: root.maximumAddressLength
                inputMethodHints: Qt.ImhNoAutoUppercase
                    | Qt.ImhNoPredictiveText | Qt.ImhUrlCharactersOnly
                activeFocusOnPress: true
                activeFocusOnTab: true
                Accessible.role: Accessible.EditableText
                Accessible.name: qsTr("Destination address")
                Accessible.description: qsTr("Place, user, path, or network address")
                font.pixelSize: Math.round(20 * touchMetrics.textScale)
                Keys.onReturnPressed: root.goToAddress()
                onActiveFocusChanged: if (activeFocus) {
                    Qt.callLater(function () {
                        DialogsManager.requestPhoneSoftwareKeyboard()
                        touchMetrics.ensureVisible(viewport, addressField)
                    })
                }
            }

            Text {
                id: addressError
                objectName: "PhoneAddressError"
                width: parent.width
                visible: text.length > 0
                color: "#ff7777"
                font.pixelSize: Math.round(18 * touchMetrics.textScale)
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }

            Grid {
                id: addressActions
                width: parent.width
                columns: touchMetrics.compact || touchMetrics.textScale > 1.25 ? 2 : 4
                columnSpacing: touchMetrics.spacingMedium
                rowSpacing: touchMetrics.spacingMedium

                HifiControls.Button {
                    objectName: "PhoneAddressBackButton"
                    width: (addressActions.width
                        - (addressActions.columns - 1) * addressActions.columnSpacing)
                        / addressActions.columns
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
                    width: (addressActions.width
                        - (addressActions.columns - 1) * addressActions.columnSpacing)
                        / addressActions.columns
                    text: qsTr("Home")
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: qsTr("Go to the home destination")
                    androidClickAction: function () { addressDialog.loadHome(); root.closeDialog() }
                }
                HifiControls.Button {
                    objectName: "PhoneAddressGoButton"
                    width: (addressActions.width
                        - (addressActions.columns - 1) * addressActions.columnSpacing)
                        / addressActions.columns
                    text: qsTr("Go")
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: qsTr("Open the entered destination")
                    androidClickAction: function () { root.goToAddress() }
                }
                HifiControls.Button {
                    objectName: "PhoneAddressCancelButton"
                    width: (addressActions.width
                        - (addressActions.columns - 1) * addressActions.columnSpacing)
                        / addressActions.columns
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
            addressField.text = ""
            addressField.deselect()
            addressField.cursorPosition = 0
            requestAddressInput()
        } else {
            Qt.inputMethod.hide()
        }
    }

    Connections {
        target: touchMetrics
        function onKeyboardVisibleChanged() {
            if (touchMetrics.keyboardVisible && addressField.activeFocus) {
                Qt.callLater(function () {
                    touchMetrics.ensureVisible(viewport, addressField)
                })
            }
        }
    }

    Component.onCompleted: {
        addressDialog.observeShownChanged(shown)
        addressError.text = ""
        addressField.text = ""
        addressField.deselect()
        addressField.cursorPosition = 0
        requestAddressInput()
    }

    Component.onDestruction: {
        addressField.focus = false
        Qt.inputMethod.hide()
    }
}
