import QtQuick 2.7

// Shared adaptive measurements for direct-touch and pointer-driven surfaces.
// Device selectors should describe capabilities here; feature UIs should use
// the derived values instead of checking a platform or device name.
QtObject {
    id: root

    property var profile: TouchUiProfile {}

    property bool directTouch: profile.directTouch
    property bool hoverSupported: profile.hoverSupported
    property bool hapticsSupported: profile.hapticsSupported
    property bool hardwareKeyboardSupported: profile.hardwareKeyboardSupported

    property real availableWidth: 0
    property real availableHeight: 0
    property real safeInsetLeft: 0
    property real safeInsetTop: 0
    property real safeInsetRight: 0
    property real safeInsetBottom: 0

    property int compactWidthLimit: 600
    property int expandedWidthLimit: 840

    readonly property real usableWidth: Math.max(0,
        availableWidth - Math.max(0, safeInsetLeft) - Math.max(0, safeInsetRight))
    readonly property real usableHeight: Math.max(0,
        availableHeight - Math.max(0, safeInsetTop) - Math.max(0, safeInsetBottom))
    readonly property bool landscape: usableWidth >= usableHeight
    readonly property string widthClass: usableWidth < compactWidthLimit
        ? "compact" : usableWidth < expandedWidthLimit ? "medium" : "expanded"
    readonly property bool compact: widthClass === "compact"
    readonly property bool expanded: widthClass === "expanded"

    // 48 logical pixels is the shared direct-touch baseline. Pointer-only
    // surfaces retain the existing compact Overte control geometry.
    readonly property int minimumTouchTarget: directTouch ? 48 : 30
    // Screen-space hosts can scale the complete QML surface. Shared controls
    // use this local value so their rendered target still reaches 48 pixels
    // without applying the host scale twice.
    readonly property int adaptiveMinimumControlHeight: directTouch
        ? Math.ceil(minimumTouchTarget /
            Math.max(1.0, profile.screenSpaceContentScale))
        : 0
    readonly property int spacingSmall: directTouch ? 8 : 4
    readonly property int spacingMedium: directTouch ? 12 : 8
    readonly property int spacingLarge: directTouch ? 24 : 16

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }

    function columnsFor(minimumCellWidth, maximumColumns, minimumColumns) {
        var lowerBound = Math.max(1, minimumColumns || 1)
        var upperBound = Math.max(lowerBound, maximumColumns || lowerBound)
        if (minimumCellWidth <= 0 || usableWidth <= 0) {
            return lowerBound
        }
        return Math.max(lowerBound, Math.min(upperBound,
            Math.floor((usableWidth + spacingSmall) /
                (minimumCellWidth + spacingSmall))))
    }
}
