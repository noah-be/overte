import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "PhoneTabletTouchConfiguration"

    property var configuration: null

    function init() {
        var path = Qt.resolvedUrl(
            "../../../../interface/resources/qml/hifi/tablet/+android_phoneInterface/TabletTouchConfiguration.qml")
        var component = Qt.createComponent(path)
        compare(component.status, Component.Ready, component.errorString())
        configuration = component.createObject(null)
        verify(configuration !== null, component.errorString())
    }

    function cleanup() {
        if (configuration) {
            configuration.destroy()
        }
        configuration = null
    }

    function test_landscapeUsesFiveColumns() {
        configuration.availableWidth = 800
        configuration.availableHeight = 400
        compare(configuration.columns, 5)
        compare(configuration.touchOptimized, true)
        compare(configuration.showCloseButton, true)
    }

    function test_portraitAndSquareUseExpectedColumns() {
        configuration.availableWidth = 400
        configuration.availableHeight = 800
        compare(configuration.columns, 3)

        configuration.availableWidth = 600
        configuration.availableHeight = 600
        compare(configuration.columns, 5)
    }

    function test_layoutValuesStayInsideTheirPhoneBounds() {
        configuration.availableWidth = 320
        configuration.availableHeight = 180
        compare(configuration.topBarHeight, 64)
        compare(configuration.horizontalMargin, 8)

        configuration.availableWidth = 2000
        configuration.availableHeight = 1000
        compare(configuration.topBarHeight, 90)
        compare(configuration.horizontalMargin, 16)
        compare(configuration.minimumTouchTarget, 48)
        compare(configuration.maximumButtonExtent, 120)
        compare(configuration.closeButtonBottomMargin, 28)
    }
}
