import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "TabletFeatureContract"

    function productionUrl(relativePath) {
        return Qt.resolvedUrl("../../../" + relativePath)
    }

    function createProductionObject(relativePath, properties) {
        var component = Qt.createComponent(productionUrl(relativePath))
        compare(component.status, Component.Ready, component.errorString())
        var object = component.createObject(null, properties || {})
        verify(object !== null, component.errorString())
        return object
    }

    function createProfile(properties) {
        return createProductionObject(
            "interface/resources/qml/controlsUit/TouchUiProfileBase.qml", properties)
    }

    function test_flatTouchCapabilitiesRemoveVrFeatures() {
        var profile = createProfile({
            directTouch: true,
            graphicsSettingsAvailable: true,
            controllerSettingsAvailable: false,
            hmdPreferencesAvailable: false,
            picoResolutionSettingsAvailable: false
        })
        var settings = createProductionObject(
            "scripts/system/settings/qml/SettingsTouchConfiguration.qml")
        settings.profile = profile
        compare(settings.showGraphicsSettings, true)
        compare(settings.showControllerSettings, false)
        compare(settings.showVrRenderResolutionSettings, false)
        compare(settings.showPicoResolutionSettings, false)
        verify(!settings.admitsSemanticControl("settings.controllers"))

        var general = createProductionObject(
            "interface/resources/qml/hifi/tablet/TabletGeneralPreferencesPolicy.qml")
        general.profile = profile
        verify(!general.admits("HMD"))
        compare(general.semanticFeatureIds, [])
        compare(Object.keys(general.categorySemanticIds), [])

        general.destroy()
        settings.destroy()
        profile.destroy()
    }

    function test_vrCapabilitiesRetainIndependentVrFeatures() {
        var profile = createProfile({
            controllerSettingsAvailable: true,
            hmdPreferencesAvailable: true,
            picoResolutionSettingsAvailable: true
        })
        var settings = createProductionObject(
            "scripts/system/settings/qml/SettingsTouchConfiguration.qml")
        settings.profile = profile
        compare(settings.showControllerSettings, true)
        compare(settings.showVrRenderResolutionSettings, true)
        verify(settings.showPicoResolutionSettings)
        verify(settings.admitsSemanticControl("settings.controllers"))

        var general = createProductionObject(
            "interface/resources/qml/hifi/tablet/TabletGeneralPreferencesPolicy.qml")
        general.profile = profile
        verify(general.admits("HMD"))
        compare(general.semanticFeatureIds, ["settings.hmd-preferences"])
        compare(general.categorySemanticIds["HMD"], "settings.hmd-preferences")

        general.destroy()
        settings.destroy()
        profile.destroy()
    }

    function test_unavailablePagesCannotBeConstructedThroughTheirFeatureGates() {
        var profile = createProfile({
            graphicsSettingsAvailable: false,
            controllerSettingsAvailable: false,
            picoResolutionSettingsAvailable: false
        })
        var settings = createProductionObject(
            "scripts/system/settings/qml/SettingsTouchConfiguration.qml")
        settings.profile = profile
        compare(settings.showGraphicsSettings, false)
        compare(settings.showControllerSettings, false)
        compare(settings.showVrRenderResolutionSettings, false)
        verify(!settings.admitsSemanticControl("settings.graphics"))
        verify(!settings.admitsSemanticControl("settings.controllers"))
        verify(!settings.admitsSemanticControl("settings.vr-render-resolution"))
        settings.destroy()
        profile.destroy()
    }

    function test_defaultPointerPresentationIsUnchanged() {
        var configuration = createProductionObject(
            "interface/resources/qml/hifi/tablet/TabletTouchConfigurationBase.qml", {
                availableWidth: 800,
                availableHeight: 600
            })
        compare(configuration.directTouch, false)
        compare(configuration.hoverSupported, true)
        compare(configuration.columns, 3)
        compare(configuration.minimumTouchTarget, 30)
        compare(configuration.showCloseButton, false)
        configuration.destroy()
    }
}
