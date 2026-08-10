import QtQuick 2.7

// The touchscreen phone client has one native Android audio context. HMD
// controls configure a separate VR path which is unavailable in this build.
QtObject {
    // A single "Desktop" tab has no navigation value and wastes scarce height.
    property bool showModeTabs: false
    property bool showVrMode: false
    // Phone has neither the desktop T-key PTT contract nor its avatar audio
    // tools overlay. Do not expose toggles that cannot be acted upon.
    property bool showPushToTalk: false
    property bool showAvatarAudioTools: false
    // WindowRoot scales this to a 50 px physical touch target.
    property int minimumControlHeight: 20
}
