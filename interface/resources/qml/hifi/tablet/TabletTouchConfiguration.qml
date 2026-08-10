import QtQuick 2.7

// Presentation knobs kept separate so platform selectors can adapt the tablet
// without copying TabletHome and drifting away from the shared Tablet API.
QtObject {
    property bool touchOptimized: false
    property real availableWidth: 0
    property real availableHeight: 0
    property int columns: 3
    property int topBarHeight: 90
    property int horizontalMargin: 30
    property int verticalMargin: 20
    property int pageIndicatorHeight: 30
    property int minimumTouchTarget: 30
    property int maximumButtonExtent: 129
    property int buttonSpacing: 0
    property bool showCloseButton: false
    property int closeButtonHeight: 0
    property int closeButtonBottomMargin: 0
}
