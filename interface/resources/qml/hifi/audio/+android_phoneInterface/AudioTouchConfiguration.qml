import QtQuick 2.7

// The touchscreen phone client has one native Android audio context. HMD
// controls configure a separate VR path which is unavailable in this build.
QtObject {
    property bool showModeTabs: false
    property bool showVrMode: false
    // WindowRoot scales this to a 50 px physical touch target.
    property int minimumControlHeight: 20
}
