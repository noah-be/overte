import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "PhoneGeneralPreferences"
    width: 640
    height: 360

    function test_phoneCategoryAndFooterPoliciesAreBounded() {
        var layoutComponent = Qt.createComponent(Qt.resolvedUrl(
            "../../../interface/resources/qml/hifi/tablet/tabletWindows/+android_phoneInterface/TabletPreferencesLayout.qml"))
        compare(layoutComponent.status, Component.Ready, layoutComponent.errorString())
        var layout = layoutComponent.createObject(null)
        verify(layout !== null)
        verify(layout.compactFooter)
        verify(layout.buttonWidth >= 48)
        verify(layout.buttonHeight > 0)

        var policyComponent = Qt.createComponent(Qt.resolvedUrl(
            "../../../interface/resources/qml/hifi/tablet/+android_phoneInterface/PhoneGeneralPreferencesPolicy.qml"))
        compare(policyComponent.status, Component.Ready, policyComponent.errorString())
        var policy = policyComponent.createObject(null)
        verify(policy !== null)
        compare(policy.allowedCategories.length, 2)
        verify(policy.admits("Navigation"))
        verify(policy.admits("Mouse Sensitivity"))
        verify(!policy.admits("User Interface"))
        verify(!policy.admits("Snapshots"))
        verify(!policy.admits("HMD"))
        verify(!policy.admits(null))
        policy.destroy()
        layout.destroy()
    }

    function test_navigationConfigurationHandlesLandscapeAndLifecycleResize() {
        var component = Qt.createComponent(Qt.resolvedUrl(
            "../../../interface/resources/qml/hifi/tablet/+android_phoneInterface/TabletTouchConfiguration.qml"))
        compare(component.status, Component.Ready, component.errorString())
        var configuration = component.createObject(null, {
            availableWidth: 800,
            availableHeight: 360
        })
        verify(configuration !== null)
        compare(configuration.columns, 5)
        verify(configuration.showCloseButton)
        verify(configuration.minimumTouchTarget >= 48)

        configuration.availableWidth = 360
        configuration.availableHeight = 800
        compare(configuration.columns, 3)
        verify(configuration.topBarHeight >= 64)
        verify(configuration.horizontalMargin >= 8)
        configuration.destroy()
    }
}
