import QtQuick 2.7

QtObject {
    property bool touchOptimized: true
    property real availableWidth: 0
    property real availableHeight: 0

    // The phone client is landscape, so use five compact columns of large
    // touch targets. Keep a portrait fallback for resize and
    // lifecycle transitions rather than depending on a fixed device size.
    property int columns: availableWidth >= availableHeight ? 5 : 3
    // WindowRoot scales this complete logical surface by 2.5. Values here are
    // deliberately unscaled layout units so every child shares one factor.
    property int topBarHeight: Math.max(64, Math.min(90, availableHeight * 0.20))
    property int horizontalMargin: Math.max(8, Math.min(16, availableWidth * 0.025))
    property int verticalMargin: 4
    property int pageIndicatorHeight: 20
    property int minimumTouchTarget: 48
    property int maximumButtonExtent: 120
    property int buttonSpacing: 5
    property bool showCloseButton: true
    property int closeButtonHeight: 32
    property int closeButtonBottomMargin: 28
}
