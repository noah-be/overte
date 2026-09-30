import QtQuick 2.12
import QtTest 1.2
import "../../../interface/resources/qml/hifi/tablet" as TabletUi

TestCase {
    id: testCase
    name: "SharedTabletNavigation"
    when: windowShown
    visible: true
    width: 1200
    height: 900

    Component { id: navigationComponent; TabletUi.TabletNavigation {} }
    Component { id: statusComponent; TabletUi.TabletPageStatus {} }
    SignalSpy { id: spy }

    function test_navigation_data() {
        return [
            {tag: "compact", surface: 320, scale: 1},
            {tag: "portrait", surface: 768, scale: 1},
            {tag: "landscape", surface: 1024, scale: 1},
            {tag: "scaled-phone", surface: 1080, scale: 2.5}
        ]
    }

    function test_navigation(data) {
        var navigation = createTemporaryObject(navigationComponent, testCase,
            {width: data.surface, contentScale: data.scale})
        verify(navigation !== null)
        ;["back", "home", "close"].forEach(function(action) {
            var button = findChild(navigation, "nav." + action)
            verify(button !== null)
            var topLeft = button.mapToItem(navigation, 0, 0)
            var bottomRight = button.mapToItem(navigation, button.width, button.height)
            verify(topLeft.x >= 0 && bottomRight.x <= navigation.width)
            verify(bottomRight.x - topLeft.x >= 48)
            verify(bottomRight.y - topLeft.y >= 48)
            spy.target = navigation
            spy.signalName = action + "Requested"
            spy.clear()
            mouseClick(button, button.width / 2, button.height / 2)
            compare(spy.count, 1)
        })
        navigation.backVisible = false
        verify(!findChild(navigation, "nav.back").visible)
        verify(findChild(navigation, "nav.home").visible)
        spy.target = null
    }

    function test_failedPageHasRecovery() {
        var status = createTemporaryObject(statusComponent, testCase,
            {width: 320, height: 400, failed: true})
        verify(status !== null)
        spy.target = status
        spy.signalName = "homeRequested"
        spy.clear()
        var home = findChild(status, "tablet.load-error.home")
        verify(home.visible)
        mouseClick(home, home.width / 2, home.height / 2)
        compare(spy.count, 1)
        spy.target = null
    }
}
