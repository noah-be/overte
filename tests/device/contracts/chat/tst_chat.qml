// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtTest 1.2
import TestChat 1.0
import "production"

Item {
    width: 480
    height: 720
    property var page: null
    SignalSpy { id: requests; target: page; signalName: "sendToScript" }
    TestCase {
        name: "NativeTabletChat"
        when: windowShown
        function init() {
            var builder = Qt.createComponent("production/armored_chat.qml")
            compare(builder.status, Component.Ready, builder.errorString())
            page = builder.createObject(parent, { width: 480, height: 720, tabletMode: true, keyboardEnabled: true })
            verify(page !== null)
            wait(30)
            page.fromScript({ type: "initial_settings", tabletMode: true, settings: {
                maximum_messages: 3, external_window: false, join_notification: false, use_chat_bubbles: false } })
            requests.clear()
        }
        function cleanup() { page.destroy(); page = null; wait(10) }
        function last() { return requests.signalArguments[requests.count - 1][0] }
        function receive(text, channel) {
            page.fromScript({ type: "show_message", message: text, displayName: "Peer", channel: channel,
                timeString: "12:00", dateString: "13 October 2026" })
        }
        function test_touchSendAndEnter() {
            var input = page.messageInput
            mouseClick(input, input.width / 2, input.height / 2)
            keyClick(Qt.Key_H); keyClick(Qt.Key_I)
            var send = findChild(page, "chatSend")
            touchEvent(send).press(0, send, send.width / 2, send.height / 2).commit()
            touchEvent(send).release(0, send, send.width / 2, send.height / 2).commit()
            compare(last().action, "end_typing")
            var messages = requests.signalArguments.filter(function(row) { return row[0].type === "send_message" })
            compare(messages.length, 1); compare(messages[0][0].message, "hi")
            compare(messages[0][0].channel, "local"); compare(input.text, "")
            input.forceActiveFocus(); keyClick(Qt.Key_A); keyClick(Qt.Key_Return)
            messages = requests.signalArguments.filter(function(row) { return row[0].type === "send_message" })
            compare(messages.length, 2); compare(messages[1][0].message, "a")
        }
        function test_boundedMixedHistoryAndClear() {
            receive("one", "local"); receive("two", "domain"); receive("three", "local"); receive("four", "domain")
            compare(page.localHistory.count, 1); compare(page.domainHistory.count, 2)
            compare(page.localHistory.get(0).text, "three")
            page.fromScript({ type: "clear_messages" })
            compare(page.localHistory.count + page.domainHistory.count, 0)
        }
        function test_richMessagesAndNarrowLayout() {
            page.width = 320; page.height = 480
            wait(20)
            receive("<hello>\nhttps://example.test/a", "domain")
            verify(page.domainHistory.get(0).text.indexOf("&lt;hello>") !== -1)
            verify(page.domainHistory.get(0).text.indexOf("<br>") !== -1)
            verify(page.domainHistory.get(0).text.indexOf("<a ") !== -1)
            var send = findChild(page, "chatSend")
            verify(send.mapToItem(page, send.width, 0).x <= page.width)
            verify(page.messageInput.width > 200)
        }
        function test_keyboardHideAndBack() {
            page.messageInput.forceActiveFocus()
            tryCompare(page, "keyboardRaised", true)
            compare(KeyboardScriptingInterface.raised, true)
            page.fromScript({ type: "chat.hidden" })
            compare(page.keyboardRaised, false); compare(KeyboardScriptingInterface.raised, false)
            var close = findChild(page, "chatClose")
            mouseClick(close, close.width / 2, close.height / 2)
            compare(last().type, "chat.close")
        }
        function test_settingsRestoreFalseAndNoFeedback() {
            compare(requests.count, 0)
            receive("a", "domain"); receive("b", "domain")
            page.fromScript({ type: "initial_settings", tabletMode: true, settings: {
                maximum_messages: 1, external_window: false, join_notification: false, use_chat_bubbles: false } })
            compare(page.domainHistory.count, 1)
            compare(requests.count, 0, "restoring settings must not write back defaults")
        }
    }
}
