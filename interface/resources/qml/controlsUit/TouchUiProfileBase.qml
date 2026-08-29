import QtQuick 2.7

// Platform-neutral UI capabilities. A device selector should override only
// these facts; shared feature configurations derive their policy and layout.
QtObject {
    property bool directTouch: false
    property bool hoverSupported: !directTouch
    property bool hapticsSupported: false
    property bool hardwareKeyboardSupported: true
    property bool systemImeAvailable: false
    property bool screenSpacePresentation: false

    property int safeInsetLeft: 0
    property int safeInsetTop: 0
    property int safeInsetRight: 0
    property int safeInsetBottom: 0
    property int imeInsetBottom: 0
    property bool keyboardVisible: false
    property int surfaceWidth: 0
    property int surfaceHeight: 0
    property real density: 1.0
    property real fontScale: 1.0
    property real screenSpaceContentScale: 1.0

    property bool audioModeTabsAvailable: true
    property bool vrAudioAvailable: true
    property bool pushToTalkAvailable: true
    property bool avatarAudioToolsAvailable: true

    property bool dominantHandSettingsAvailable: true
    property bool hmdAlignmentAvailable: true
    property bool externalAvatarCatalogAvailable: true
    property bool scriptingPluginsAvailable: true

    property bool graphicsSettingsAvailable: true
    property bool controllerSettingsAvailable: true
    // Legacy selectors still own the product-named implementation flag. New
    // shared consumers expose only this capability-neutral projection.
    property bool picoResolutionSettingsAvailable: true
    readonly property bool vrRenderResolutionAvailable: picoResolutionSettingsAvailable

    property bool navigationPreferencesAvailable: false
    property bool userInterfacePreferencesAvailable: true
    property bool hmdPreferencesAvailable: true
    property bool snapshotPreferencesAvailable: true
    property bool privacyPreferencesAvailable: true
    property bool pluginPreferencesAvailable: true
}
