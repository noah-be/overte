import QtQuick 2.12
import QtTest 1.2

TestCase {
    id: testCase
    name: "PhoneEmote"
    width: 640
    height: 360

    property var emote: null

    Item {
        id: host
        anchors.fill: parent
    }

    function init() {
        testCase.width = 640
        testCase.height = 360
        var path = Qt.resolvedUrl(
            "../../../../scripts/system/+android_phoneInterface/PhoneEmote.qml")
        var component = Qt.createComponent(path)
        compare(component.status, Component.Ready, component.errorString())
        emote = component.createObject(host)
        verify(emote !== null, component.errorString())
        wait(0)
    }

    function cleanup() {
        if (emote) {
            emote.destroy()
        }
        emote = null
    }

    function test_exposesReviewedEmoteSet() {
        compare(emote.emotes.length, 10)
        compare(emote.emotes[0], "Crying")
        compare(emote.emotes[4], "Waving")
        compare(emote.emotes[9], "Love")
        compare(emote.activeEmote, "")
        compare(emote.statusText, "Choose an emote")
    }

    function test_acceptsNamespacedStateFromScript() {
        emote.fromScript({
            method: "phoneEmote.state",
            active: "Dancing",
            status: "Playing Dancing"
        })
        compare(emote.activeEmote, "Dancing")
        compare(emote.statusText, "Playing Dancing")
    }

    function test_rejectsUnrelatedAndMalformedState() {
        emote.fromScript({ method: "unrelated", active: "Waving", status: "wrong" })
        compare(emote.activeEmote, "")
        compare(emote.statusText, "Choose an emote")

        emote.fromScript(null)
        compare(emote.activeEmote, "")

        emote.fromScript({ method: "phoneEmote.state", active: 42, status: "" })
        compare(emote.activeEmote, "")
        compare(emote.statusText, "Choose an emote")
    }

    function test_partialAndEmptyStateUsesIndependentFallbacks() {
        emote.fromScript({ method: "phoneEmote.state", active: "Love" })
        compare(emote.activeEmote, "Love")
        compare(emote.statusText, "Choose an emote")

        emote.fromScript({ method: "phoneEmote.state", active: "", status: "Stopped" })
        compare(emote.activeEmote, "")
        compare(emote.statusText, "Stopped")

        emote.fromScript({ method: "phoneEmote.state", active: null, status: 7 })
        compare(emote.activeEmote, "")
        compare(emote.statusText, "Choose an emote")
    }

    function test_buttonEmitsNamespacedPlayMessage() {
        var messages = []
        emote.sendToScript.connect(function(message) { messages.push(message) })
        wait(50)
        var button = findChild(emote, "PhoneEmoteButton_Crying")
        verify(button !== null)
        button.clicked()
        compare(messages.length, 1)
        compare(messages[0].method, "phoneEmote.play")
        compare(messages[0].name, "Crying")
    }

    function test_accessibilitySemanticsTrackSelectionState() {
        wait(50)
        var crying = findChild(emote, "PhoneEmoteButton_Crying")
        var status = findChild(emote, "PhoneEmoteStatus")
        verify(crying !== null)
        verify(status !== null)
        compare(crying.Accessible.role, Accessible.Button)
        compare(crying.Accessible.name, "Crying")
        compare(crying.Accessible.description, "Play emote")
        verify(crying.activeFocusOnTab)
        compare(status.Accessible.role, Accessible.StaticText)
        compare(status.Accessible.name, "Choose an emote")

        emote.fromScript({
            method: "phoneEmote.state",
            active: "Crying",
            status: "Playing Crying"
        })
        compare(crying.Accessible.description, "Currently playing emote")
        compare(status.Accessible.name, "Playing Crying")
    }

    function test_gridReflowsAcrossCompactMediumAndExpandedWidths() {
        var grid = findChild(emote, "PhoneEmoteGrid")
        verify(grid !== null)

        testCase.width = 360
        wait(0)
        compare(grid.adaptiveColumns, 2)
        verify(grid.cellWidth >= 150)

        testCase.width = 500
        wait(0)
        compare(grid.adaptiveColumns, 3)

        testCase.width = 700
        wait(0)
        compare(grid.adaptiveColumns, 4)
        verify(grid.cellHeight >= 48 / 2.5)
    }
}
