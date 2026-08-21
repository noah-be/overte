import QtQuick 2.7
import "../../controlsUit" as HifiControls

HifiControls.TouchUiMetrics {
    readonly property bool favoritesFillBelowHeader: profile.screenSpacePresentation
    readonly property bool showDominantHand: profile.dominantHandSettingsAvailable
    readonly property bool showHmdAlignment: profile.hmdAlignmentAvailable
    readonly property bool showGetMoreAvatars: profile.externalAvatarCatalogAvailable
    readonly property int settingsRightMargin: profile.screenSpacePresentation ? 12 : 32
    readonly property int settingsBottomMargin: profile.screenSpacePresentation ? 12 : 57
}
