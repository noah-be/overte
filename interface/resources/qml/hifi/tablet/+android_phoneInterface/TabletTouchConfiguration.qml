import QtQuick 2.7

QtObject {
    property bool touchOptimized: true
    property real availableWidth: 0
    property real availableHeight: 0

    // The phone client is landscape, so use the width for two compact rows of
    // the existing twelve-button page. Keep a portrait fallback for resize and
    // lifecycle transitions rather than depending on a fixed device size.
    property int columns: availableWidth >= availableHeight ? 6 : 3
    property int topBarHeight: Math.max(64, Math.min(90, availableHeight * 0.20))
    property int horizontalMargin: Math.max(16, Math.min(32, availableWidth * 0.025))
    property int verticalMargin: 12
    property int pageIndicatorHeight: 48
    property int minimumTouchTarget: 48
    property int maximumButtonExtent: 144
}
