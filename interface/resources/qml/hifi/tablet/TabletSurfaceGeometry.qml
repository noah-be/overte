import QtQuick 2.7

QtObject {
    property var profile
    readonly property real x: profile.screenSpaceOriginAtSafeArea ? 0 : profile.safeInsetLeft
    readonly property real y: profile.screenSpaceOriginAtSafeArea ? 0 : profile.safeInsetTop
    readonly property real width: Math.max(1,
        profile.surfaceWidth - profile.safeInsetLeft - profile.safeInsetRight)
    readonly property real height: Math.max(1, profile.surfaceHeight - profile.safeInsetTop
        - Math.max(profile.safeInsetBottom, profile.imeInsetBottom))
    readonly property bool valid: profile.surfaceWidth > profile.safeInsetLeft + profile.safeInsetRight
        && profile.surfaceHeight > profile.safeInsetTop + Math.max(profile.safeInsetBottom, profile.imeInsetBottom)
}
