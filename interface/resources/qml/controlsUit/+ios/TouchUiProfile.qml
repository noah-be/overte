import QtQuick 2.7
import OverteIOS 1.0

TouchUiProfileBase {
    readonly property var runtimeMetrics: IOSTouchUiMetrics

    directTouch: true
    hoverSupported: false
    hapticsSupported: true
    hardwareKeyboardSupported: false
    systemImeAvailable: true
    screenSpacePresentation: true

    safeInsetLeft: runtimeMetrics.safeInsetLeft
    safeInsetTop: runtimeMetrics.safeInsetTop
    safeInsetRight: runtimeMetrics.safeInsetRight
    safeInsetBottom: runtimeMetrics.safeInsetBottom
    imeInsetBottom: runtimeMetrics.imeInsetBottom
    keyboardVisible: runtimeMetrics.keyboardVisible
    surfaceWidth: runtimeMetrics.surfaceWidth
    surfaceHeight: runtimeMetrics.surfaceHeight
    density: runtimeMetrics.density
    fontScale: runtimeMetrics.fontScale
    screenSpaceContentScale: 1.0

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
