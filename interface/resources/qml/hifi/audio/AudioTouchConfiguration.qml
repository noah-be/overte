import QtQuick 2.7
import "../../controlsUit" as HifiControls

HifiControls.TouchUiMetrics {
    readonly property bool showModeTabs: profile.audioModeTabsAvailable
    readonly property bool showVrMode: profile.vrAudioAvailable
    readonly property bool showPushToTalk: profile.pushToTalkAvailable
    readonly property bool showAvatarAudioTools: profile.avatarAudioToolsAvailable
    readonly property int minimumControlHeight: directTouch
        ? Math.max(20, adaptiveMinimumControlHeight)
        : 16
}
