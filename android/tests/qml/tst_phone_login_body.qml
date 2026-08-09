import QtQuick 2.12
import QtTest 1.2

TestCase {
    id: testCase
    name: "PhoneLoginBody"
    width: 640
    height: 360

    property var body: null
    property int loginCalls: 0
    property int domainLoginCalls: 0
    property int dismissCalls: 0
    property int destroyCalls: 0
    property string submittedUsername: ""
    property string submittedPassword: ""
    property bool domainRequested: false
    property string requestedDomain: ""
    property bool pending: false

    Item {
        id: host
        anchors.fill: parent

        Item {
            id: root
            anchors.fill: parent
            function tryDestroy() { testCase.destroyCalls += 1 }
        }

        QtObject {
            id: loginDialog
            signal handleLoginCompleted()
            signal handleLoginFailed()

            function getDomainLoginRequested() { return testCase.domainRequested }
            function getDomainLoginDomain() { return testCase.requestedDomain }
            function isPhoneLoginRequestPending() { return testCase.pending }
            function dismissPhoneLoginDialog() { testCase.dismissCalls += 1 }
            function login(username, password) {
                testCase.loginCalls += 1
                testCase.submittedUsername = username
                testCase.submittedPassword = password
            }
            function loginDomain(username, password) {
                testCase.domainLoginCalls += 1
                testCase.submittedUsername = username
                testCase.submittedPassword = password
            }
        }
    }

    function createBody() {
        var path = Qt.resolvedUrl(
            "../../../interface/resources/qml/LoginDialog/+android_phoneInterface/LinkAccountBody.qml")
        var component = Qt.createComponent(path)
        compare(component.status, Component.Ready, component.errorString())
        body = component.createObject(root)
        verify(body !== null, component.errorString())
        wait(0)
    }

    function init() {
        loginCalls = 0
        domainLoginCalls = 0
        dismissCalls = 0
        destroyCalls = 0
        submittedUsername = ""
        submittedPassword = ""
        domainRequested = false
        requestedDomain = ""
        pending = false
        createBody()
    }

    function cleanup() {
        if (body) {
            body.destroy()
            wait(0)
        }
        body = null
    }

    function field(name) {
        var result = findChild(body, name)
        verify(result !== null, "missing " + name)
        return result
    }

    function test_emptyCredentialsFailClosed() {
        body.submit()
        compare(loginCalls, 0)
        compare(domainLoginCalls, 0)
        verify(field("PhoneLoginError").text.length > 0)

        field("PhoneLoginUsername").text = "alice"
        body.submit()
        compare(loginCalls, 0)
        verify(field("PhoneLoginError").text.length > 0)
    }

    function test_accountLoginAndDuplicateSubmissionSuppression() {
        field("PhoneLoginUsername").text = "alice@example.com"
        field("PhoneLoginPassword").text = "secret"
        body.submit()
        compare(loginCalls, 1)
        compare(domainLoginCalls, 0)
        compare(submittedUsername, "alice@example.com")
        compare(submittedPassword, "secret")
        verify(body.waiting)
        verify(body.requestSubmitted)
        body.submit()
        compare(loginCalls, 1)
    }

    function test_domainLoginUsesDomainBackend() {
        body.destroy()
        body = null
        domainRequested = true
        requestedDomain = "example.test"
        createBody()
        verify(body.domainLogin)
        compare(body.domainName, "example.test")
        field("PhoneLoginUsername").text = "domain-user"
        field("PhoneLoginPassword").text = "password"
        body.submit()
        compare(domainLoginCalls, 1)
        compare(loginCalls, 0)
    }

    function test_failedSubmittedLoginRestoresFormAndExplainsFailure() {
        field("PhoneLoginUsername").text = "alice"
        field("PhoneLoginPassword").text = "wrong"
        body.submit()
        loginDialog.handleLoginFailed()
        verify(!body.waiting)
        verify(!body.requestSubmitted)
        compare(field("PhoneLoginError").text, "Username or password incorrect.")
        compare(field("PhoneLoginPassword").text, "wrong")
    }

    function test_unsolicitedFailureOnlyClearsPendingState() {
        pending = true
        body.destroy()
        body = null
        createBody()
        verify(body.waiting)
        loginDialog.handleLoginFailed()
        verify(!body.waiting)
        compare(field("PhoneLoginError").text, "")
    }

    function test_completionDismissesAndScrubsPasswordOnce() {
        field("PhoneLoginUsername").text = "alice"
        field("PhoneLoginPassword").text = "secret"
        body.submit()
        loginDialog.handleLoginCompleted()
        compare(dismissCalls, 1)
        compare(destroyCalls, 1)
        compare(field("PhoneLoginPassword").text, "")
        verify(body.closing)
        loginDialog.handleLoginCompleted()
        body.dismiss()
        compare(dismissCalls, 1)
        compare(destroyCalls, 1)
    }

    function test_cancelActionDismissesAndIsIdempotent() {
        field("PhoneLoginPassword").text = "secret"
        var cancel = field("PhoneLoginCancel")
        verify(typeof cancel.androidClickAction === "function")
        cancel.androidClickAction()
        compare(dismissCalls, 1)
        compare(destroyCalls, 1)
        compare(field("PhoneLoginPassword").text, "")
        cancel.androidClickAction()
        compare(dismissCalls, 1)
    }

    function test_credentialLengthIsBounded() {
        var oversized = new Array(body.maximumCredentialLength + 20).join("x")
        field("PhoneLoginUsername").text = oversized
        field("PhoneLoginPassword").text = oversized
        compare(field("PhoneLoginUsername").text.length, body.maximumCredentialLength)
        compare(field("PhoneLoginPassword").text.length, body.maximumCredentialLength)
    }

    function test_accessibilitySemanticsCoverCredentialsAndActions() {
        var username = field("PhoneLoginUsername")
        var password = field("PhoneLoginPassword")
        var submit = field("PhoneLoginSubmit")
        var cancel = field("PhoneLoginCancel")
        compare(username.Accessible.role, Accessible.EditableText)
        compare(username.Accessible.name, "Username or email")
        verify(username.Accessible.description.length > 0)
        verify(username.activeFocusOnTab)
        compare(password.Accessible.role, Accessible.EditableText)
        verify(password.Accessible.passwordEdit)
        verify(password.activeFocusOnTab)
        compare(submit.Accessible.role, Accessible.Button)
        compare(submit.Accessible.name, "Log in")
        verify(submit.Accessible.description.length > 0)
        verify(submit.activeFocusOnTab)
        compare(cancel.Accessible.role, Accessible.Button)
        compare(cancel.Accessible.name, "Cancel")
        verify(cancel.Accessible.description.length > 0)
        verify(cancel.activeFocusOnTab)
        compare(field("PhoneLoginError").Accessible.role, Accessible.StaticText)
    }

    function test_passwordAccessibilityNeverExposesCredentials() {
        var username = field("PhoneLoginUsername")
        var password = field("PhoneLoginPassword")
        username.text = "private-user@example.test"
        password.text = "correct horse battery staple"

        compare(password.echoMode, TextInput.Password)
        verify(password.Accessible.passwordEdit)
        verify(password.Accessible.name.indexOf(username.text) < 0)
        verify(password.Accessible.name.indexOf(password.text) < 0)
        verify(password.Accessible.description.indexOf(username.text) < 0)
        verify(password.Accessible.description.indexOf(password.text) < 0)
    }

    function test_keyboardFocusStartsOnUsernameAndFailureMovesToPassword() {
        verify(field("PhoneLoginUsername").focus)
        field("PhoneLoginUsername").text = "alice"
        field("PhoneLoginPassword").text = "wrong"
        body.submit()
        loginDialog.handleLoginFailed()
        verify(field("PhoneLoginPassword").focus)
    }
}
