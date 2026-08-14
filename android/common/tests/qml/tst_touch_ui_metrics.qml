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

        metrics.hoverSupported = false
        compare(metrics.hoverSupported, false)
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
}
