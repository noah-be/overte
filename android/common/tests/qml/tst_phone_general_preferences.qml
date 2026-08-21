import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "PhoneGeneralPreferences"
    width: 640
    height: 360

    function createProductionComponent(relativePath) {
        var component = Qt.createComponent(Qt.resolvedUrl("../../../../" + relativePath))
        compare(component.status, Component.Ready, component.errorString())
        return component
    }

    function createPhoneProfile() {
        var component = createProductionComponent(
            "interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml")
        var profile = component.createObject(null)
        verify(profile !== null, component.errorString())
        return profile
    }

    function test_phoneCategoryAndFooterPoliciesAreBounded() {
        var phoneProfile = createPhoneProfile()
        var layoutComponent = createProductionComponent(
            "interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesLayout.qml")
        var layout = layoutComponent.createObject(null, { profile: phoneProfile })
        verify(layout !== null)
        verify(layout.compactFooter)
        verify(layout.buttonWidth >= 48)
        verify(layout.buttonHeight > 0)

        var policyComponent = createProductionComponent(
            "interface/resources/qml/hifi/tablet/TabletGeneralPreferencesPolicy.qml")
        var policy = policyComponent.createObject(null, { profile: phoneProfile })
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
        phoneProfile.destroy()
    }

    function test_navigationConfigurationHandlesLandscapeAndLifecycleResize() {
        var phoneProfile = createPhoneProfile()
        var component = createProductionComponent(
            "interface/resources/qml/hifi/tablet/TabletTouchConfiguration.qml")
        var configuration = component.createObject(null, {
            profile: phoneProfile,
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
        phoneProfile.destroy()
    }
}
