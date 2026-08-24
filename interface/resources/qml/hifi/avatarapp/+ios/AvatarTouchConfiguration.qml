import QtQuick 2.7
import "../../../controlsUit" as HifiControls

// The iOS selector must win over the Android phone compatibility selector:
// Avatar Settings binds availableWidth/availableHeight for adaptive layout.
HifiControls.TouchUiMetrics {
    readonly property bool favoritesFillBelowHeader: profile.screenSpacePresentation
    readonly property bool showDominantHand: profile.dominantHandSettingsAvailable
    readonly property bool showHmdAlignment: profile.hmdAlignmentAvailable
    readonly property bool showGetMoreAvatars: profile.externalAvatarCatalogAvailable
    readonly property int settingsRightMargin: profile.screenSpacePresentation ? 12 : 32
    readonly property int settingsBottomMargin: profile.screenSpacePresentation ? 12 : 57
    Component.onCompleted: console.log(
        "OVERTE_IOS_TOUCH_UI_GATE stage=avatar-ios-selector-ready")
}
