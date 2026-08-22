// Phone-only, screen-space login body. The generic Android selector targets
// standalone HMDs and assumes tablet-sized geometry and completion pages.
import Hifi 1.0
import QtQuick 2.7
import controlsUit 1.0 as HifiControls

Item {
    id: phoneLogin
    objectName: "PhoneLoginBody"
    anchors.fill: parent

    readonly property bool domainLogin: loginDialog.getDomainLoginRequested()
    readonly property string domainName: loginDialog.getDomainLoginDomain()
    // OverlayLoginDialog supplies these initial properties for platform login
    // providers. Phone MVP authentication intentionally ignores both flows,
    // but declaring them keeps Loader.setSource() free of property errors.
    property bool linkSteam: false
    property bool linkOculus: false
    property bool waiting: loginDialog.isPhoneLoginRequestPending()
    property bool requestSubmitted: false
    property bool closing: false
    property bool keyDismissPending: false
    readonly property int maximumCredentialLength: 4096

    function dismiss() {
        if (closing) {
            return
        }
        closing = true
        password.text = ""
        Qt.inputMethod.hide()
        phoneLogin.forceActiveFocus()
        loginDialog.dismissPhoneLoginDialog()
        root.tryDestroy()
    }

    function submit() {
        if (waiting || closing) {
            return
        }
        if (username.text.length === 0 || password.text.length === 0) {
            errorText.text = qsTr("Enter a username and password.")
            return
        }
        errorText.text = ""
        waiting = true
        requestSubmitted = true
        Qt.inputMethod.hide()
        if (domainLogin) {
            loginDialog.loginDomain(username.text, password.text)
        } else {
            loginDialog.login(username.text, password.text)
        }
    }

    Flickable {
        id: viewport
        anchors.fill: parent
        anchors.leftMargin: Math.min(24, parent.width / 4)
        anchors.rightMargin: anchors.leftMargin
        anchors.topMargin: Math.min(24, parent.height / 4)
        anchors.bottomMargin: anchors.topMargin
        contentWidth: width
        contentHeight: Math.max(height, panel.height)
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Rectangle {
            anchors.fill: panel
            radius: 18
            color: "#e6282d33"
            border.color: "#6679858e"
        }

        Column {
            id: panel
            width: Math.min(viewport.width, 560)
            x: (viewport.width - width) / 2
            y: Math.max(0, (viewport.height - height) / 2)
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
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }

            Text {
                id: errorText
                objectName: "PhoneLoginError"
                width: parent.width
                visible: text.length > 0
                color: "#ff7777"
                font.pixelSize: 18
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }

            HifiControls.TextField {
                id: username
                objectName: "PhoneLoginUsername"
                width: parent.width
                height: 52
                placeholderText: qsTr("Username or email")
                maximumLength: phoneLogin.maximumCredentialLength
                enabled: !phoneLogin.waiting
                activeFocusOnPress: true
                activeFocusOnTab: true
                Accessible.role: Accessible.EditableText
                Accessible.name: qsTr("Username or email")
                Accessible.description: phoneLogin.domainLogin
                    ? qsTr("Domain account username or email")
                    : qsTr("Overte account username or email")
                font.pixelSize: 20
                Keys.onReturnPressed: password.forceActiveFocus()
            }

            HifiControls.TextField {
                id: password
                objectName: "PhoneLoginPassword"
                width: parent.width
                height: 52
                placeholderText: qsTr("Password")
                maximumLength: phoneLogin.maximumCredentialLength
                echoMode: TextInput.Password
                enabled: !phoneLogin.waiting
                activeFocusOnPress: true
                activeFocusOnTab: true
                Accessible.role: Accessible.EditableText
                Accessible.name: qsTr("Password")
                Accessible.description: qsTr("Account password")
                Accessible.passwordEdit: true
                font.pixelSize: 20
                Keys.onReturnPressed: phoneLogin.submit()
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 16

                HifiControls.Button {
                    objectName: "PhoneLoginSubmit"
                    text: phoneLogin.waiting ? qsTr("Logging in…") : qsTr("Log in")
                    enabled: !phoneLogin.waiting
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: phoneLogin.domainLogin
                        ? qsTr("Submit domain login")
                        : qsTr("Submit Overte login")
                    androidClickAction: function () { phoneLogin.submit() }
                }

                HifiControls.Button {
                    objectName: "PhoneLoginCancel"
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.description: qsTr("Close login without signing in")
                    androidClickAction: function () {
                        phoneLogin.dismiss()
                    }
                }
            }
        }
    }

    Connections {
        target: loginDialog
        function onHandleLoginCompleted() {
            if (phoneLogin.closing) {
                return
            }
            phoneLogin.waiting = false
            phoneLogin.dismiss()
        }
        function onHandleLoginFailed() {
            if (phoneLogin.closing) {
                return
            }
            if (!phoneLogin.requestSubmitted) {
                phoneLogin.waiting = false
                return
            }
            phoneLogin.waiting = false
            phoneLogin.requestSubmitted = false
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
    Component.onDestruction: {
        closing = true
        keyDismissPending = false
        username.text = ""
        password.text = ""
        errorText.text = ""
        Qt.inputMethod.hide()
    }
}
