// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.12
import QtTest 1.2

TestCase {
    id: testCase
    name: "PhoneDomainLoginRecovery"
    width: 640
    height: 360
    property var body: null
    property int domainLoginCalls: 0
    property int dismissCalls: 0
    property int destroyCalls: 0
    property bool domainRequested: false
    property string requestedDomain: ""
    Item {
        id: root
        anchors.fill: parent
        function tryDestroy() { testCase.destroyCalls += 1 }
    }
    QtObject {
        id: loginDialog
        signal handleLoginCompleted()
        signal handleLoginFailed()
        signal handleDomainLoginFailed(string reason)
        function getDomainLoginRequested() { return testCase.domainRequested }
        function getDomainLoginDomain() { return testCase.requestedDomain }
        function isPhoneLoginRequestPending() { return false }
        function dismissPhoneLoginDialog() { testCase.dismissCalls += 1 }
        function login(username, password) { fail("Domain retry used account transport") }
        function loginDomain(username, password) { testCase.domainLoginCalls += 1 }
    }
    function createBody() {
        var component = Qt.createComponent(Qt.resolvedUrl("production/PhoneLoginBody.qml"))
        compare(component.status, Component.Ready, component.errorString())
        body = component.createObject(root)
        verify(body !== null, component.errorString())
        wait(0)
    }
    function field(name) {
        var item = findChild(body, name)
        verify(item !== null, "missing " + name)
        return item
    }
    function init() {
        domainLoginCalls = 0
        dismissCalls = 0
        destroyCalls = 0
        domainRequested = false
        requestedDomain = ""
        createBody()
    }
    function cleanup() {
        if (body) body.destroy()
        body = null
        wait(0)
    }

    function submitDomainLogin() {
        body.destroy()
        body = null
        domainRequested = true
        requestedDomain = "example.test"
        createBody()
        field("PhoneLoginUsername").text = "domain-user"
        field("PhoneLoginPassword").text = "retained-for-retry"
        body.submit()
        verify(body.waiting && body.requestSubmitted)
        compare(domainLoginCalls, 1)
    }

    function test_domainFailureRestoresActionableRetry() {
        // A domain callback must not disturb an account login.
        loginDialog.handleDomainLoginFailed("failed")
        compare(field("PhoneLoginError").text, "")
        submitDomainLogin()
        loginDialog.handleDomainLoginFailed("failed")
        verify(!body.waiting && !body.requestSubmitted)
        verify(!body.closing)
        compare(dismissCalls, 0)
        verify(field("PhoneLoginError").text.indexOf("credentials") >= 0)
        verify(field("PhoneLoginPassword").focus)
        compare(field("PhoneLoginPassword").selectedText, "retained-for-retry")
        body.submit()
        compare(domainLoginCalls, 2)
        verify(body.waiting && body.requestSubmitted)
    }

    function test_domainTimeoutExplainsFailureAndAllowsRetry() {
        submitDomainLogin()
        loginDialog.handleDomainLoginFailed("timeout")
        verify(!body.waiting && !body.requestSubmitted)
        verify(!body.closing)
        compare(dismissCalls, 0)
        verify(field("PhoneLoginError").text.indexOf("timed out") >= 0)
        verify(field("PhoneLoginPassword").focus)
        body.submit()
        compare(domainLoginCalls, 2)
    }

    function test_domainCancellationDismissesAndIgnoresLateFailure() {
        submitDomainLogin()
        loginDialog.handleDomainLoginFailed("cancelled")
        verify(body.closing)
        verify(!body.waiting && !body.requestSubmitted)
        compare(dismissCalls, 1)
        compare(destroyCalls, 1)
        compare(field("PhoneLoginPassword").text, "")
        loginDialog.handleDomainLoginFailed("timeout")
        loginDialog.handleDomainLoginFailed("failed")
        compare(dismissCalls, 1)
        compare(destroyCalls, 1)
        compare(field("PhoneLoginError").text, "")
    }

}
