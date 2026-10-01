import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "PhoneTabletTouchConfiguration"

    property var configuration: null
    property var profile: null

    function init() {
        var profileComponent = Qt.createComponent(Qt.resolvedUrl("DirectTouchHostProfile.qml"))
        compare(profileComponent.status, Component.Ready, profileComponent.errorString())
        profile = profileComponent.createObject(null)
        verify(profile !== null, profileComponent.errorString())
        var path = Qt.resolvedUrl(
            "../../../../interface/resources/qml/hifi/tablet/TabletTouchConfiguration.qml")
        var component = Qt.createComponent(path)
        compare(component.status, Component.Ready, component.errorString())
        configuration = component.createObject(null, { profile: profile })
        verify(configuration !== null, component.errorString())
    }

    function cleanup() {
        if (configuration) {
            configuration.destroy()
        }
        configuration = null
        if (profile) { profile.destroy() }
        profile = null
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
        compare(configuration.horizontalMargin, 24)
        configuration.availableWidth = 800
        compare(configuration.horizontalMargin, 16)
        compare(configuration.minimumTouchTarget, 48)
        compare(configuration.maximumButtonExtent, 120)
        compare(configuration.closeButtonBottomMargin, 28)
        compare(configuration.closeButtonHeight, 32)
        profile.screenSpaceContentScale = 1
        compare(configuration.closeButtonHeight, 48)
        profile.screenSpaceContentScale = 2.5
        compare(configuration.closeButtonHeight, 32)
        profile.stackedTabletHeader = true
        compare(configuration.topBarHeight, 116)
        profile.fontScale = 1.5
        compare(configuration.topBarHeight, 140)
        profile.fontScale = 3
        compare(configuration.topBarHeight, 140)
    }
}
