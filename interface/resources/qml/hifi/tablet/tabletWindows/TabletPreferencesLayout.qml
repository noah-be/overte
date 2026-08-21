import QtQuick 2.7
import "../../../controlsUit" as HifiControls

HifiControls.TouchUiMetrics {
    readonly property bool compactFooter: profile.screenSpacePresentation
    property int buttonWidth: 120
    property int buttonHeight: 28
    property int buttonFontSize: 9
    property int buttonSpacing: 11
}
