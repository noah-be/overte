// Phone-only, screen-space login body. The generic Android selector targets
// standalone HMDs and assumes tablet-sized geometry and completion pages.
import Hifi 1.0
import QtQuick 2.7
import QtQuick.Controls 1.4
import controlsUit 1.0 as HifiControls

Item {
    id: phoneLogin
    anchors.fill: parent

    readonly property bool domainLogin: loginDialog.getDomainLoginRequested()
    readonly property string domainName: loginDialog.getDomainLoginDomain()
    // OverlayLoginDialog supplies these initial properties for platform login
    // providers. Phone MVP authentication intentionally ignores both flows,
    // but declaring them keeps Loader.setSource() free of property errors.
    property bool linkSteam: false
    property bool linkOculus: false
    property bool waiting: false
    property bool closing: false
    property bool keyDismissPending: false

    function dismiss() {
        if (closing) {
            return
        }
        closing = true
        Qt.inputMethod.hide()
        loginDialog.dismissPhoneLoginDialog()
        root.tryDestroy()
    }

    function submit() {
        if (username.text.length === 0 || password.text.length === 0) {
            errorText.text = qsTr("Enter a username and password.")
            return
        }
        errorText.text = ""
        waiting = true
        Qt.inputMethod.hide()
        if (domainLogin) {
            loginDialog.loginDomain(username.text, password.text)
        } else {
            loginDialog.login(username.text, password.text)
        }
    }

    Rectangle {
        anchors.fill: panel
        radius: 18
        color: "#e6282d33"
        border.color: "#6679858e"
    }

    Column {
        id: panel
        width: Math.min(parent.width - 48, 560)
        anchors.centerIn: parent
        spacing: 18

        Text {
            width: parent.width
            text: phoneLogin.domainLogin
                ? qsTr("Log in to %1").arg(phoneLogin.domainName)
                : qsTr("Log in to Overte")
            color: "white"
            font.pixelSize: 28
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            id: errorText
            width: parent.width
            visible: text.length > 0
            color: "#ff7777"
            font.pixelSize: 18
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
        }

        HifiControls.TextField {
            id: username
            width: parent.width
            height: 52
            placeholderText: qsTr("Username or email")
            enabled: !phoneLogin.waiting
            activeFocusOnPress: true
            font.pixelSize: 20
            Keys.onReturnPressed: password.forceActiveFocus()
        }

        HifiControls.TextField {
            id: password
            width: parent.width
            height: 52
            placeholderText: qsTr("Password")
            echoMode: TextInput.Password
            enabled: !phoneLogin.waiting
            activeFocusOnPress: true
            font.pixelSize: 20
            Keys.onReturnPressed: phoneLogin.submit()
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 16

            HifiControls.Button {
                text: phoneLogin.waiting ? qsTr("Logging in…") : qsTr("Log in")
                enabled: !phoneLogin.waiting
                androidClickAction: function () { phoneLogin.submit() }
            }

            HifiControls.Button {
                text: qsTr("Cancel")
                androidClickAction: function () {
                    phoneLogin.dismiss()
                }
            }
        }
    }

    Connections {
        target: loginDialog
        function onHandleLoginCompleted() {
            phoneLogin.waiting = false
            phoneLogin.dismiss()
        }
        function onHandleLoginFailed() {
            phoneLogin.waiting = false
            errorText.text = phoneLogin.domainLogin
                ? qsTr("Domain login failed.")
                : qsTr("Username or password incorrect.")
            password.selectAll()
            password.forceActiveFocus()
        }
    }

    Keys.onPressed: {
        if (event.key === Qt.Key_Back || event.key === Qt.Key_Escape) {
            // Handle this before the generic LoginDialog.qml handler, which
            // accepts Back without closing anything.
            event.accepted = true
            keyDismissPending = true
            Qt.inputMethod.hide()
        }
    }

    Keys.onReleased: {
        if (event.key === Qt.Key_Back || event.key === Qt.Key_Escape) {
            // Keep the matching release out of Application as well; otherwise
            // it could be interpreted as an unmatched request to go Home.
            event.accepted = true
            if (keyDismissPending) {
                keyDismissPending = false
                phoneLogin.dismiss()
            }
        }
    }

    Component.onCompleted: username.forceActiveFocus()
}
