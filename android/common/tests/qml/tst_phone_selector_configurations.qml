import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "PhoneCapabilityConfigurations"

    function productionUrl(relativePath) {
        return Qt.resolvedUrl("../../../../" + relativePath)
    }

    function createProductionObject(relativePath, properties) {
        var component = Qt.createComponent(productionUrl(relativePath))
        compare(component.status, Component.Ready, component.errorString())
        var object = component.createObject(null, properties || {})
        verify(object !== null, component.errorString())
        return object
    }

    function createPhoneConfiguration(relativePath) {
        var profile = createProductionObject(
            "interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml")
        var configuration = createProductionObject(relativePath, { profile: profile })
        return { profile: profile, configuration: configuration }
    }

    function destroyFixture(fixture) {
        fixture.configuration.destroy()
        fixture.profile.destroy()
    }

    function test_audioConfigurationDisablesUnavailableDesktopAndVrControls() {
        var fixture = createPhoneConfiguration(
            "interface/resources/qml/hifi/audio/AudioTouchConfiguration.qml")
        var configuration = fixture.configuration
        compare(configuration.showModeTabs, false)
        compare(configuration.showVrMode, false)
        compare(configuration.showPushToTalk, false)
        compare(configuration.showAvatarAudioTools, false)
        compare(configuration.minimumControlHeight, 20)
        destroyFixture(fixture)
    }

    function test_avatarConfigurationKeepsPhoneLayoutAndHidesTrackedInput() {
        var fixture = createPhoneConfiguration(
            "interface/resources/qml/hifi/avatarapp/AvatarTouchConfiguration.qml")
        var configuration = fixture.configuration
        compare(configuration.favoritesFillBelowHeader, true)
        compare(configuration.showDominantHand, false)
        compare(configuration.showHmdAlignment, false)
        compare(configuration.showGetMoreAvatars, false)
        compare(configuration.settingsRightMargin, 12)
        compare(configuration.settingsBottomMargin, 12)
        destroyFixture(fixture)
    }

    function test_securityConfigurationUsesCompactPhoneGeometry() {
        var fixture = createPhoneConfiguration(
            "interface/resources/qml/hifi/dialogs/security/SecurityTouchConfiguration.qml")
        var configuration = fixture.configuration
        compare(configuration.showScriptingPlugins, false)
        compare(configuration.titleHeight, 44)
        compare(configuration.headerHeight, 40)
        compare(configuration.rowHeight, 56)
        compare(configuration.buttonHeight, 44)
        destroyFixture(fixture)
    }

    function test_preferencesConfigurationDoesNotCompoundHostScale() {
        var fixture = createPhoneConfiguration(
            "interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesLayout.qml")
        var configuration = fixture.configuration
        compare(configuration.compactFooter, true)
        compare(configuration.buttonWidth, 120)
        compare(configuration.buttonHeight, 28)
        compare(configuration.buttonFontSize, 9)
        compare(configuration.buttonSpacing, 11)
        destroyFixture(fixture)
    }

    function test_settingsConfigurationKeepsBoundedPhonePages() {
        var fixture = createPhoneConfiguration(
            "scripts/system/settings/qml/SettingsTouchConfiguration.qml")
        var configuration = fixture.configuration
        compare(configuration.contentScale, 1.0)
        compare(configuration.showGraphicsSettings, false)
        compare(configuration.showControllerSettings, false)
        compare(configuration.showPicoResolutionSettings, false)
        destroyFixture(fixture)
    }
}
