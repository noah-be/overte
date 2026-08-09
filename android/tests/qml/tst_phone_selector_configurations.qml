import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "PhoneSelectorConfigurations"

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

    function test_audioSelectorDisablesUnavailableDesktopAndVrControls() {
        var configuration = createProductionObject(
            "interface/resources/qml/hifi/audio/+android_phoneInterface/AudioTouchConfiguration.qml")
        compare(configuration.showModeTabs, false)
        compare(configuration.showVrMode, false)
        compare(configuration.showPushToTalk, false)
        compare(configuration.showAvatarAudioTools, false)
        compare(configuration.minimumControlHeight, 20)
        configuration.destroy()
    }

    function test_avatarSelectorKeepsPhoneLayoutAndHidesTrackedInput() {
        var configuration = createProductionObject(
            "interface/resources/qml/hifi/avatarapp/+android_phoneInterface/AvatarTouchConfiguration.qml")
        compare(configuration.favoritesFillBelowHeader, true)
        compare(configuration.showDominantHand, false)
        compare(configuration.showHmdAlignment, false)
        compare(configuration.showGetMoreAvatars, false)
        compare(configuration.settingsRightMargin, 12)
        compare(configuration.settingsBottomMargin, 12)
        configuration.destroy()
    }

    function test_securitySelectorUsesCompactPhoneGeometry() {
        var configuration = createProductionObject(
            "interface/resources/qml/hifi/dialogs/security/+android_phoneInterface/SecurityTouchConfiguration.qml")
        compare(configuration.showScriptingPlugins, false)
        compare(configuration.titleHeight, 44)
        compare(configuration.headerHeight, 40)
        compare(configuration.rowHeight, 56)
        compare(configuration.buttonHeight, 44)
        configuration.destroy()
    }

    function test_preferencesSelectorDoesNotCompoundHostScale() {
        var configuration = createProductionObject(
            "interface/resources/qml/hifi/tablet/tabletWindows/+android_phoneInterface/TabletPreferencesLayout.qml")
        compare(configuration.compactFooter, true)
        compare(configuration.buttonWidth, 120)
        compare(configuration.buttonHeight, 28)
        compare(configuration.buttonFontSize, 9)
        compare(configuration.buttonSpacing, 11)
        configuration.destroy()
    }

    function test_settingsSelectorKeepsBoundedPhonePages() {
        var configuration = createProductionObject(
            "scripts/system/settings/qml/+android_phoneInterface/SettingsTouchConfiguration.qml")
        compare(configuration.contentScale, 1.0)
        compare(configuration.showGraphicsSettings, false)
        compare(configuration.showControllerSettings, false)
        compare(configuration.showPicoResolutionSettings, false)
        configuration.destroy()
    }
}
