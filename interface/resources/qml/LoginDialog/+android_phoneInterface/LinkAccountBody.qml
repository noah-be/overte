// Phone-only, screen-space login body. The generic Android selector targets
// standalone HMDs and assumes tablet-sized geometry and completion pages.
import Hifi 1.0
import QtQuick 2.7
import QtQuick.Controls 1.4
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

    HifiControls.TouchUiMetrics {
        id: touchMetrics
        availableWidth: phoneLogin.width
        availableHeight: phoneLogin.height
    }

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
        anchors.leftMargin: Math.min(touchMetrics.spacingLarge, parent.width / 4)
        anchors.rightMargin: anchors.leftMargin
        anchors.topMargin: Math.min(touchMetrics.spacingLarge, parent.height / 4)
        anchors.bottomMargin: anchors.topMargin
        contentWidth: width
        contentHeight: Math.max(height, panel.height)
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        pressDelay: touchMetrics.pressDelay
        flickDeceleration: touchMetrics.flickDeceleration
        maximumFlickVelocity: touchMetrics.maximumFlickVelocity

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
                font.pixelSize: Math.round(28 * touchMetrics.textScale)
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
                font.pixelSize: Math.round(18 * touchMetrics.textScale)
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }

            HifiControls.TextField {
                id: username
                objectName: "PhoneLoginUsername"
                width: parent.width
                height: Math.max(52, implicitHeight)
                placeholderText: qsTr("Username or email")
                maximumLength: phoneLogin.maximumCredentialLength
                inputMethodHints: Qt.ImhEmailCharactersOnly | Qt.ImhNoAutoUppercase
                enabled: !phoneLogin.waiting
                activeFocusOnPress: true
                activeFocusOnTab: true
                Accessible.role: Accessible.EditableText
                Accessible.name: qsTr("Username or email")
                Accessible.description: phoneLogin.domainLogin
                    ? qsTr("Domain account username or email")
                    : qsTr("Overte account username or email")
                font.pixelSize: Math.round(20 * touchMetrics.textScale)
                Keys.onReturnPressed: password.forceActiveFocus()
                onActiveFocusChanged: if (activeFocus) {
                    Qt.callLater(function () {
                        touchMetrics.ensureVisible(viewport, username)
                    })
                }
            }

            HifiControls.TextField {
                id: password
                objectName: "PhoneLoginPassword"
                width: parent.width
                height: Math.max(52, implicitHeight)
                placeholderText: qsTr("Password")
                maximumLength: phoneLogin.maximumCredentialLength
                echoMode: TextInput.Password
                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText
                    | Qt.ImhHiddenText
                enabled: !phoneLogin.waiting
                activeFocusOnPress: true
                activeFocusOnTab: true
                Accessible.role: Accessible.EditableText
                Accessible.name: qsTr("Password")
                Accessible.description: qsTr("Account password")
                Accessible.passwordEdit: true
                font.pixelSize: Math.round(20 * touchMetrics.textScale)
                Keys.onReturnPressed: phoneLogin.submit()
                onActiveFocusChanged: if (activeFocus) {
                    Qt.callLater(function () {
                        touchMetrics.ensureVisible(viewport, password)
                    })
                }
            }

            Row {
                id: loginActions
                width: parent.width
                spacing: touchMetrics.spacingMedium

                HifiControls.Button {
                    objectName: "PhoneLoginSubmit"
                    text: phoneLogin.waiting ? qsTr("Logging in…") : qsTr("Log in")
                    width: (loginActions.width - loginActions.spacing) / 2
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
                    width: (loginActions.width - loginActions.spacing) / 2
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

    Connections {
        target: touchMetrics
        function onKeyboardVisibleChanged() {
            var focusedField = username.activeFocus ? username
                : password.activeFocus ? password : null
            if (touchMetrics.keyboardVisible && focusedField) {
                Qt.callLater(function () {
                    touchMetrics.ensureVisible(viewport, focusedField)
                })
            }
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
