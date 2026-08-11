import QtQuick 2.12
import QtTest 1.2
import Hifi 1.0

TestCase {
    name: "PhoneComponentLifecycleEndurance"
    width: 900
    height: 500

    Item {
        id: host
        anchors.fill: parent
    }

    function load(path) {
        var component = Qt.createComponent(Qt.resolvedUrl(path))
        compare(component.status, Component.Ready, component.errorString())
        return component
    }

    function test_repeatedCreateInteractDestroyReleasesOwnedObjects() {
        var emoteComponent = load("../../../../scripts/system/+android_phoneInterface/PhoneEmote.qml")
        var addressComponent = load("../../../../interface/resources/qml/+android_phoneInterface/AddressBarDialog.qml")
        var touchComponent = load("../../../../interface/resources/qml/hifi/tablet/+android_phoneInterface/TabletTouchConfiguration.qml")
        var baselineChildren = host.children.length

        for (var cycle = 0; cycle < 200; ++cycle) {
            DialogsManager.reset()
            AddressManager.reset()
            var emote = emoteComponent.createObject(host)
            var address = addressComponent.createObject(host)
            var touch = touchComponent.createObject(host, {
                availableWidth: cycle % 2 ? 360 : 800,
                availableHeight: cycle % 2 ? 800 : 360
            })
            verify(emote !== null, emoteComponent.errorString())
            verify(address !== null, addressComponent.errorString())
            verify(touch !== null, touchComponent.errorString())

            var emitted = 0
            emote.sendToScript.connect(function() { emitted += 1 })
            emote.fromScript({ method: "phoneEmote.state", active: "Waving", status: "Playing" })
            compare(emote.activeEmote, "Waving")
            address.shown = false
            address.shown = true
            touch.availableWidth = 400 + cycle
            verify(touch.columns >= 3)

            emote.destroy()
            address.destroy()
            touch.destroy()
            wait(0)
            compare(host.children.length, baselineChildren,
                    "owned QML objects leaked after cycle " + cycle)
        }
    }

    function test_childAccountingObservesAndReleasesResidualOwnership() {
        var baselineChildren = host.children.length
        var sentinelComponent = Qt.createComponent("../qml/imports/controlsUit/Button.qml")
        compare(sentinelComponent.status, Component.Ready, sentinelComponent.errorString())
        var sentinel = sentinelComponent.createObject(host)
        verify(sentinel !== null)
        compare(host.children.length, baselineChildren + 1,
                "the endurance ownership check must observe a retained child")
        sentinel.destroy()
        wait(0)
        compare(host.children.length, baselineChildren,
                "destroyed sentinel must leave the ownership registry")
    }
}
