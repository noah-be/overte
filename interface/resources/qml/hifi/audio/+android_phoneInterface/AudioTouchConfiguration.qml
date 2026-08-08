import QtQuick 2.7

// The touchscreen phone client has one native Android audio context. HMD
// controls configure a separate VR path which is unavailable in this build.
QtObject {
    // Keep the single native context tab visible: Qt Quick Controls uses the
    // TabBar geometry while laying out the legacy Audio form.
    property bool showModeTabs: true
    property bool showVrMode: false
    // WindowRoot scales this to a 50 px physical touch target.
    property int minimumControlHeight: 20
}
