import QtQuick 2.7
import "../../controlsUit" as HifiControls

// Shared system-tablet presentation. Platform selectors should only provide
// capabilities such as directTouch and screenSpacePresentation.
HifiControls.TouchUiMetrics {
    id: root

    readonly property bool touchOptimized: directTouch
    property int columns: directTouch
        ? (compact ? 3 : expanded ? 6 : 5)
        : 3
    property int topBarHeight: directTouch
        ? clamp(availableHeight * 0.20, 64, 90)
        : 90
    property int horizontalMargin: directTouch
        ? clamp(availableWidth * 0.025, 8, expanded ? 24 : 16)
        : 30
    property int verticalMargin: directTouch ? 4 : 20
    property int pageIndicatorHeight: directTouch ? 20 : 30
    property int maximumButtonExtent: directTouch ? 120 : 129
    property int buttonSpacing: directTouch ? 5 : 0
    property bool showCloseButton: directTouch && profile.screenSpacePresentation
    property int closeButtonHeight: showCloseButton ? 32 : 0
    property int closeButtonBottomMargin: showCloseButton ? 28 : 0
}
