import QtQuick 2.7
import "../../../controlsUit" as HifiControls

// iOS inherits most of the Android phone presentation, but its audio page
// consumes adaptive dimensions that the Android-only selector does not expose.
HifiControls.TouchUiMetrics {
    readonly property bool showModeTabs: profile.audioModeTabsAvailable
    readonly property bool showVrMode: profile.vrAudioAvailable
    readonly property bool showPushToTalk: profile.pushToTalkAvailable
    readonly property bool showAvatarAudioTools: profile.avatarAudioToolsAvailable
    readonly property int minimumControlHeight: directTouch
        ? Math.max(20, adaptiveMinimumControlHeight, Math.ceil(20 * textScale))
        : 16
}
