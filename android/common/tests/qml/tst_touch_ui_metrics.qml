import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "TouchUiMetrics"

    property var metrics: null

    function productionUrl(relativePath) {
        return Qt.resolvedUrl("../../../../" + relativePath)
    }

    function createProductionObject(relativePath, properties) {
        var component = Qt.createComponent(productionUrl(relativePath))
        compare(component.status, Component.Ready, component.errorString())
        var object = component.createObject(null, properties || {})
        verify(object !== null, component.errorString())
        return object
    }

    function init() {
        metrics = createProductionObject(
            "interface/resources/qml/controlsUit/TouchUiMetrics.qml")
    }

    function cleanup() {
        if (metrics) {
            metrics.destroy()
        }
        metrics = null
    }

    function test_pointerDefaultsPreserveCompactDesktopControls() {
        compare(metrics.directTouch, false)
        compare(metrics.hoverSupported, true)
        compare(metrics.minimumTouchTarget, 30)
        compare(metrics.adaptiveMinimumControlHeight, 0)
        compare(metrics.spacingSmall, 4)
    }

    function test_directTouchUsesSharedMinimumsWithoutDiscardingHybridHover() {
        metrics.directTouch = true
        compare(metrics.hoverSupported, true)
        compare(metrics.minimumTouchTarget, 48)
        compare(metrics.adaptiveMinimumControlHeight, 48)
        compare(metrics.spacingSmall, 8)
        compare(metrics.pressDelay, 80)
        compare(metrics.flickDeceleration, 4000)
        compare(metrics.maximumFlickVelocity, 8000)

        metrics.hoverSupported = false
        compare(metrics.hoverSupported, false)
    }

    function test_fontScaleAndSystemImeCapabilitiesRemainBounded() {
        compare(metrics.systemImeAvailable, false)
        metrics.profile.fontScale = 0.5
        compare(metrics.textScale, 1.0)
        metrics.profile.fontScale = 2.0
        compare(metrics.textScale, 1.5)
        metrics.profile.systemImeAvailable = true
        compare(metrics.systemImeAvailable, true)
    }

    function test_focusRevealScrollsOnlyAsFarAsNeeded() {
        var flickable = Qt.createQmlObject(
            'import QtQuick 2.12; Flickable {'
                + 'width: 200; height: 100; contentWidth: 200; contentHeight: 400;'
                + 'Item { objectName: "focusTarget"; y: 300; width: 20; height: 30 }'
                + '}', this)
        verify(flickable !== null)
        var target = findChild(flickable, "focusTarget")
        verify(target !== null)

        metrics.ensureVisible(flickable, target, 10)
        compare(flickable.contentY, 240)

        target.y = 5
        metrics.ensureVisible(flickable, target, 10)
        compare(flickable.contentY, 0)

        metrics.ensureVisible(null, target, 10)
        metrics.ensureVisible(flickable, null, 10)
        flickable.destroy()
    }

    function test_representativeLogicalSurfaceMatrixStaysBounded() {
        var devices = [
            { width: 320, height: 568, left: 0, right: 0, expected: "compact" },
            { width: 640, height: 360, left: 24, right: 16, expected: "medium" },
            { width: 900, height: 600, left: 30, right: 30, expected: "expanded" },
            { width: 840, height: 840, left: 1, right: 0, expected: "medium" },
            { width: 1200, height: 720, left: 100, right: 300, expected: "medium" }
        ]
        metrics.directTouch = true
        for (var index = 0; index < devices.length; ++index) {
            var device = devices[index]
            metrics.availableWidth = device.width
            metrics.availableHeight = device.height
            metrics.safeInsetLeft = device.left
            metrics.safeInsetRight = device.right
            metrics.safeInsetTop = 0
            metrics.safeInsetBottom = 0
            compare(metrics.widthClass, device.expected)
            verify(metrics.usableWidth >= 0)
            verify(metrics.columnsFor(120, 6, 1) >= 1)
            verify(metrics.columnsFor(120, 6, 1) <= 6)
        }
    }

    function test_widthClassesFollowUsableSafeArea() {
        metrics.availableWidth = 620
        metrics.availableHeight = 500
        compare(metrics.widthClass, "medium")

        metrics.safeInsetLeft = 20
        metrics.safeInsetRight = 20
        metrics.safeInsetTop = 10
        metrics.safeInsetBottom = 20
        compare(metrics.usableWidth, 580)
        compare(metrics.usableHeight, 470)
        compare(metrics.widthClass, "compact")
        compare(metrics.landscape, true)

        metrics.availableWidth = 900
        compare(metrics.widthClass, "expanded")
    }

    function test_gridColumnsAreBounded() {
        metrics.directTouch = true
        metrics.availableWidth = 320
        compare(metrics.columnsFor(120, 6, 2), 2)

        metrics.availableWidth = 800
        compare(metrics.columnsFor(120, 6, 2), 6)

        compare(metrics.columnsFor(0, 6, 3), 3)
    }

    function test_defaultTabletAdapterRemainsPointerDriven() {
        var tabletConfiguration = createProductionObject(
            "interface/resources/qml/hifi/tablet/TabletTouchConfiguration.qml")
        compare(tabletConfiguration.touchOptimized, false)
        compare(tabletConfiguration.columns, 3)
        compare(tabletConfiguration.topBarHeight, 90)
        compare(tabletConfiguration.horizontalMargin, 30)
        compare(tabletConfiguration.showCloseButton, false)
        tabletConfiguration.destroy()
    }

    function test_phoneProfileCentralizesDeviceCapabilitiesAndHostGeometry() {
        var phoneProfile = createProductionObject(
            "interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml")
        compare(phoneProfile.directTouch, true)
        compare(phoneProfile.hoverSupported, false)
        compare(phoneProfile.hapticsSupported, true)
        compare(phoneProfile.hardwareKeyboardSupported, false)
        compare(phoneProfile.systemImeAvailable, true)
        compare(phoneProfile.screenSpacePresentation, true)
        compare(phoneProfile.safeInsetLeft, 25)
        compare(phoneProfile.safeInsetTop, 25)
        compare(phoneProfile.safeInsetRight, 25)
        compare(phoneProfile.safeInsetBottom, 25)
        compare(phoneProfile.screenSpaceContentScale, 2.5)
        compare(phoneProfile.graphicsSettingsAvailable, false)
        compare(phoneProfile.navigationPreferencesAvailable, true)

        var phoneMetrics = createProductionObject(
            "interface/resources/qml/controlsUit/TouchUiMetrics.qml",
            { profile: phoneProfile })
        compare(phoneMetrics.adaptiveMinimumControlHeight, 20)
        phoneMetrics.destroy()
        phoneProfile.destroy()
    }

    function test_phoneProfileConsumesLiveInsetsImeDensityAndHybridInput() {
        var runtime = {
            valid: true,
            surfaceWidth: 2400,
            surfaceHeight: 1080,
            safeInsetLeft: 92,
            safeInsetTop: 7,
            safeInsetRight: 31,
            safeInsetBottom: 24,
            imeInsetBottom: 420,
            density: 2.75,
            fontScale: 1.2,
            contentScale: 2.75,
            keyboardVisible: true,
            hoverSupported: true,
            hardwareKeyboardSupported: true,
            hapticsSupported: false
        }
        var phoneProfile = createProductionObject(
            "interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml",
            { runtimeMetrics: runtime })
        compare(phoneProfile.runtimeMetricsAvailable, true)
        compare(phoneProfile.surfaceWidth, 2400)
        compare(phoneProfile.surfaceHeight, 1080)
        compare(phoneProfile.safeInsetLeft, 92)
        compare(phoneProfile.safeInsetTop, 7)
        compare(phoneProfile.safeInsetRight, 31)
        compare(phoneProfile.safeInsetBottom, 24)
        compare(phoneProfile.imeInsetBottom, 420)
        compare(phoneProfile.keyboardVisible, true)
        compare(phoneProfile.hoverSupported, true)
        compare(phoneProfile.hardwareKeyboardSupported, true)
        compare(phoneProfile.hapticsSupported, false)
        compare(phoneProfile.density, 2.75)
        compare(phoneProfile.fontScale, 1.2)
        compare(phoneProfile.screenSpaceContentScale, 2.75)

        var liveMetrics = createProductionObject(
            "interface/resources/qml/controlsUit/TouchUiMetrics.qml",
            { profile: phoneProfile })
        compare(liveMetrics.keyboardVisible, true)
        compare(liveMetrics.keyboardInsetBottom, 420)
        compare(liveMetrics.textScale, 1.2)
        compare(liveMetrics.adaptiveMinimumControlHeight, 18)
        liveMetrics.destroy()
        phoneProfile.destroy()
    }
}
