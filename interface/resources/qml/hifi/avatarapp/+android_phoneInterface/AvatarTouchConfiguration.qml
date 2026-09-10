import QtQuick 2.7
import controlsUit 1.0 as HifiControls

// Phone presentation is screen-space and has no HMD or tracked-hand input.
HifiControls.TouchUiMetrics {
    readonly property bool favoritesFillBelowHeader: true
    readonly property bool showDominantHand: false
    readonly property bool showHmdAlignment: false
    readonly property bool showGetMoreAvatars: false
    readonly property int settingsRightMargin: 12
    readonly property int settingsBottomMargin: 12
}
