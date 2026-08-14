import QtQuick 2.7
import ".." as SharedControls

// Android Phone is the first device adapter for the universal touch UI. New
// devices should add one equivalent profile rather than copy feature screens.
SharedControls.TouchUiProfileBase {
    property var runtimeMetrics: typeof Tablet !== "undefined"
        && Tablet && Tablet.touchUiRuntimeMetrics
        ? Tablet.touchUiRuntimeMetrics : ({})
    readonly property bool runtimeMetricsAvailable: runtimeMetrics
        && runtimeMetrics.valid === true

    directTouch: true
    hoverSupported: runtimeMetricsAvailable
        ? runtimeMetrics.hoverSupported === true : false
    hapticsSupported: runtimeMetricsAvailable
        ? runtimeMetrics.hapticsSupported === true : true
    hardwareKeyboardSupported: runtimeMetricsAvailable
        ? runtimeMetrics.hardwareKeyboardSupported === true : false
    systemImeAvailable: true
    screenSpacePresentation: true

    // Live Android measurements replace these conservative startup defaults
    // as soon as the Qt host accepts its first runtime snapshot.
    safeInsetLeft: runtimeMetricsAvailable ? runtimeMetrics.safeInsetLeft : 25
    safeInsetTop: runtimeMetricsAvailable ? runtimeMetrics.safeInsetTop : 25
    safeInsetRight: runtimeMetricsAvailable ? runtimeMetrics.safeInsetRight : 25
    safeInsetBottom: runtimeMetricsAvailable ? runtimeMetrics.safeInsetBottom : 25
    imeInsetBottom: runtimeMetricsAvailable ? runtimeMetrics.imeInsetBottom : 0
    keyboardVisible: runtimeMetricsAvailable
        ? runtimeMetrics.keyboardVisible === true : false
    surfaceWidth: runtimeMetricsAvailable ? runtimeMetrics.surfaceWidth : 0
    surfaceHeight: runtimeMetricsAvailable ? runtimeMetrics.surfaceHeight : 0
    density: runtimeMetricsAvailable ? runtimeMetrics.density : 2.5
    fontScale: runtimeMetricsAvailable ? runtimeMetrics.fontScale : 1.0
    screenSpaceContentScale: runtimeMetricsAvailable
        ? runtimeMetrics.contentScale : 2.5

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
