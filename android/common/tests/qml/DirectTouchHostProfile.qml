import QtQuick 2.7
import "../../../../interface/resources/qml/controlsUit" as SharedControls

// A bounded host capability fixture for shared configurations. The Phone lane
// additionally loads its real product-selected profile and runtime metrics.
SharedControls.TouchUiProfileBase {
    directTouch: true
    hapticsSupported: true
    hardwareKeyboardSupported: false
    systemImeAvailable: true
    screenSpacePresentation: true
    screenSpaceContentScale: 2.5
    stackedTabletHeader: false
    audioModeTabsAvailable: false
    vrAudioAvailable: false
    pushToTalkAvailable: false
    avatarAudioToolsAvailable: false
    dominantHandSettingsAvailable: false
    hmdAlignmentAvailable: false
    externalAvatarCatalogAvailable: false
    scriptingPluginsAvailable: false
    controllerSettingsAvailable: false
    graphicsSettingsAvailable: false
    picoResolutionSettingsAvailable: false
    navigationPreferencesAvailable: true
    userInterfacePreferencesAvailable: false
    hmdPreferencesAvailable: false
    snapshotPreferencesAvailable: false
    privacyPreferencesAvailable: false
    pluginPreferencesAvailable: false
}
