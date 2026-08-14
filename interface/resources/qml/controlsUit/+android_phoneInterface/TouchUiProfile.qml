import QtQuick 2.7
import ".." as SharedControls

// Android Phone is the first device adapter for the universal touch UI. New
// devices should add one equivalent profile rather than copy feature screens.
SharedControls.TouchUiProfileBase {
    directTouch: true
    hoverSupported: false
    hapticsSupported: true
    hardwareKeyboardSupported: false
    screenSpacePresentation: true

    // The current Phone host uses a uniform rounded-corner guard and scales
    // the complete legacy tablet surface. These can later come from Android
    // WindowInsets/display metrics without changing any feature UI.
    safeInsetLeft: 25
    safeInsetTop: 25
    safeInsetRight: 25
    safeInsetBottom: 25
    screenSpaceContentScale: 2.5

    audioModeTabsAvailable: false
    vrAudioAvailable: false
    pushToTalkAvailable: false
    avatarAudioToolsAvailable: false

    dominantHandSettingsAvailable: false
    hmdAlignmentAvailable: false
    externalAvatarCatalogAvailable: false
    scriptingPluginsAvailable: false

    graphicsSettingsAvailable: false
    controllerSettingsAvailable: false
    picoResolutionSettingsAvailable: false

    navigationPreferencesAvailable: true
    userInterfacePreferencesAvailable: false
    hmdPreferencesAvailable: false
    snapshotPreferencesAvailable: false
    privacyPreferencesAvailable: false
    pluginPreferencesAvailable: false
}
