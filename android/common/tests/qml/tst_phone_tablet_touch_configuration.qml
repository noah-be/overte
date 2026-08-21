import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "PhoneTabletTouchConfiguration"

    property var configuration: null
    property var phoneProfile: null

    function init() {
        var profileComponent = Qt.createComponent(Qt.resolvedUrl(
            "../../../../interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml"))
        compare(profileComponent.status, Component.Ready, profileComponent.errorString())
        phoneProfile = profileComponent.createObject(null)
        verify(phoneProfile !== null, profileComponent.errorString())

        var component = Qt.createComponent(Qt.resolvedUrl(
            "../../../../interface/resources/qml/hifi/tablet/TabletTouchConfiguration.qml"))
        compare(component.status, Component.Ready, component.errorString())
        configuration = component.createObject(null, { profile: phoneProfile })
        verify(configuration !== null, component.errorString())
    }

    function cleanup() {
        if (configuration) {
            configuration.destroy()
        }
        configuration = null
        if (phoneProfile) {
            phoneProfile.destroy()
        }
        phoneProfile = null
    }

    function test_landscapeUsesFiveColumns() {
        configuration.availableWidth = 800
        configuration.availableHeight = 400
        compare(configuration.columns, 5)
        compare(configuration.touchOptimized, true)
        compare(configuration.widthClass, "medium")
        compare(configuration.hoverSupported, false)
        compare(configuration.hapticsSupported, true)
        compare(configuration.hardwareKeyboardSupported, false)
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

    function test_expandedTouchSurfaceUsesSixColumns() {
        configuration.availableWidth = 1000
        configuration.availableHeight = 700
        compare(configuration.widthClass, "expanded")
        compare(configuration.columns, 6)
    }

    function test_layoutValuesStayInsideTheirPhoneBounds() {
        configuration.availableWidth = 320
        configuration.availableHeight = 180
        compare(configuration.topBarHeight, 64)
        compare(configuration.horizontalMargin, 8)

        configuration.availableWidth = 2000
        configuration.availableHeight = 1000
        compare(configuration.topBarHeight, 90)
        compare(configuration.horizontalMargin, 24)
        compare(configuration.minimumTouchTarget, 48)
        compare(configuration.maximumButtonExtent, 120)
        compare(configuration.closeButtonBottomMargin, 28)
    }
}
