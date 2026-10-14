// SPDX-License-Identifier: Apache-2.0
// The Pico controller ray delivers ordinary Qt mouse events to this shared surface.
import QtQuick 2.7
import QtTest 1.2

Item {
    width: 480
    height: 720

    Loader {
        id: emotePage
        anchors.fill: parent
        source: "../../../../../scripts/system/+android_phoneInterface/PhoneEmote.qml"
    }

    SignalSpy {
        id: messages
        target: emotePage.item
        signalName: "sendToScript"
    }

    TestCase {
        name: "PicoNativeEmote"
        when: windowShown && emotePage.status === Loader.Ready

        function test_controllerPointerClicksAndState() {
            var names = ["Crying", "Surprised", "Dancing", "Cheering", "Waving",
                         "Fall", "Pointing", "Clapping", "Sit", "Love"]
            for (var i = 0; i < names.length; i++) {
                var button = findChild(emotePage.item, "PhoneEmoteButton_" + names[i])
                verify(button !== null, "Each bundled emote has a native button")
                verify(button.width >= 100 && button.height >= 40,
                       "Controller targets remain large at tablet dimensions")
                messages.clear()
                mouseClick(button, button.width / 2, button.height / 2)
                compare(messages.count, 1)
                compare(messages.signalArguments[0][0].method, "phoneEmote.play")
                compare(messages.signalArguments[0][0].name, names[i])
            }
            emotePage.item.fromScript({ method: "phoneEmote.state", active: "Waving",
                                       status: "Playing Waving" })
            compare(emotePage.item.activeEmote, "Waving")
            compare(findChild(emotePage.item, "PhoneEmoteStatus").text, "Playing Waving")
            verify(findChild(emotePage.item, "PhoneEmoteButton_Waving").highlighted)
            emotePage.item.fromScript({ method: "phoneEmote.state", active: "",
                                       status: "Choose an emote" })
            verify(!findChild(emotePage.item, "PhoneEmoteButton_Waving").highlighted)
        }
    }
}
