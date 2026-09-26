import QtQuick 2.12
import QtTest 1.2
import "../../../interface/resources/qml/hifi/tablet" as TabletUi
import "../../../interface/resources/qml/controlsUit" as Controls

TestCase {
    name: "TabletSurfaceGeometry"
    Component { id: profileComponent; Controls.TouchUiProfileBase {} }
    Component { id: geometryComponent; TabletUi.TabletSurfaceGeometry {} }

    function test_rotationKeyboardAndNativeOrigin() {
        var profile = createTemporaryObject(profileComponent, this, {
            surfaceWidth: 768, surfaceHeight: 1024,
            safeInsetLeft: 8, safeInsetRight: 12, safeInsetTop: 24, safeInsetBottom: 20
        })
        var geometry = createTemporaryObject(geometryComponent, this, {profile: profile})
        verify(geometry.valid)
        compare(geometry.x, 8)
        compare(geometry.y, 24)
        compare(geometry.width, 748)
        compare(geometry.height, 980)
        profile.screenSpaceOriginAtSafeArea = true
        compare(geometry.x, 0)
        compare(geometry.y, 0)
        compare(geometry.width, 748)
        profile.surfaceWidth = 1024
        profile.surfaceHeight = 768
        profile.imeInsetBottom = 300
        compare(geometry.width, 1004)
        compare(geometry.height, 444)
        profile.imeInsetBottom = 0
        compare(geometry.height, 724)
        profile.surfaceWidth = 0
        verify(!geometry.valid)
        compare(geometry.width, 1)
    }
}
