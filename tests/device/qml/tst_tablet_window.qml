import QtQuick 2.12
import QtTest 1.2
import "../../../interface/resources/qml/hifi/tablet" as TabletUi
import "../../../scripts/system/places" as Places

TestCase {
    id: testCase
    name: "WholeTabletNavigation"
    when: windowShown
    visible: true
    width: 1400
    height: 1400
    readonly property string homeSource: "hifi/tablet/TabletHome.qml"
    readonly property string placesSource: "scripts/system/places/PicoPlaces.qml"
    property var currentWindow: null
    // Only the native desktop, page-loading and TabletProxy service boundaries
    // are substituted. WindowRoot, ScrollingWindow and Places are production QML.
    QtObject {
        id: desktop
        property int invalid_position: -10000
        property bool gradientsSupported: false
        property bool pinned: false
        signal hmdHandMouseActiveChanged()
        function centerOnVisible(window) { window.x = 0; window.y = 0 }
        function repositionOnVisible(window) {}
        function raise(window) {}
    }
    QtObject { id: eventBridge; signal webEventReceived(var message) }
    QtObject {
        id: proxy
        property int homes: 0
        property int closes: 0
        property bool tabletShown: false
        function gotoHomeScreen() { homes++; currentWindow.loadSource(homeSource) }
        function hideAndroidTablet() {
            closes++
            currentWindow.setShown(false)
            tabletShown = false
        }
        function loadQMLSource(source) { currentWindow.loadSource(source) }
    }
    QtObject {
        id: surface
        signal qmlLoadFailed(var parent, int generation)
        function load(source, parent, callback) {
            if (source === "broken.qml") {
                qmlLoadFailed(parent, parent.qmlLoadGeneration)
                return
            }
            var factory = source === placesSource ? placesFactory : homeFactory
            callback(factory.createObject(parent))
        }
    }
    Component { id: homeFactory; Item {} }
    Component { id: placesFactory; Places.PicoPlaces {} }
    Component {
        id: windowFactory
        TabletUi.WindowRoot {
            tabletProxy: proxy
            pageSurface: surface
        }
    }

    function init() { proxy.homes = 0; proxy.closes = 0; proxy.tabletShown = false }
    function cleanup() { currentWindow = null }

    function openTablet() {
        var window = createTemporaryObject(windowFactory, testCase)
        verify(window !== null)
        currentWindow = window
        window.setScreenSpaceMode(true)
        window.loadSource(placesSource)
        window.setShown(true)
        proxy.tabletShown = true
        tryCompare(window, "opacity", 1)
        return window
    }

    function test_windowHideReleasesTabletState() {
        var window = openTablet()
        // A host/window close bypasses the footer's hideAndroidTablet call.
        // The native proxy must still notify mobileActionBar to release input.
        window.setShown(false)
        compare(proxy.tabletShown, false)
        compare(proxy.closes, 1)
        tryCompare(window, "visible", false)
        window.setShown(false)
        compare(proxy.closes, 1)
    }

    function test_reopenDuringFade_data() {
        return [
            {tag: "touch", screenSpace: true},
            {tag: "desktop", screenSpace: false}
        ]
    }

    function test_reopenDuringFade(data) {
        var window = openTablet()
        window.setScreenSpaceMode(data.screenSpace)
        for (var cycle = 0; cycle < 3; ++cycle) {
            // Also cancel a close before the first animation frame is drawn.
            window.setShown(false)
            window.setShown(true)
            proxy.tabletShown = true
            wait(350)
            compare(window.opacity, 1)
            window.setShown(false)
            tryVerify(function() { return window.opacity > 0 && window.opacity < 1 })
            window.setShown(true)
            proxy.tabletShown = true
            tryCompare(window, "opacity", 1)
            verify(window.visible)
            verify(window.shown)
        }
    }

    function test_desktopHideDoesNotOwnTouchState() {
        var window = openTablet()
        window.setScreenSpaceMode(false)
        window.setShown(false)
        compare(proxy.closes, 0)
        compare(proxy.tabletShown, true)
    }

    function test_repeatedNavigationAndClose() {
        var window = openTablet()
        findChild(window, "tabletTouchProfile").directTouch = true
        var loader = findChild(window, "loader")
        for (var cycle = 0; cycle < 3; ++cycle) {
            proxy.gotoHomeScreen()
            verify(window.shown)
            verify(proxy.tabletShown)
            window.loadSource(placesSource)
            tryVerify(function() { return window.footer.visible })
            var close = findChild(window.footer, "nav.close")
            mouseClick(close, close.width / 2, close.height / 2)
            verify(!window.shown)
            verify(!proxy.tabletShown)
            tryCompare(window, "visible", false)
            window.setShown(true)
            proxy.tabletShown = true
            tryCompare(window, "opacity", 1)
            compare(loader.source, placesSource)
        }
    }

    function verifyNavigation(window, loader) {
        ;["back", "home", "close"].forEach(function(action) {
            var button = findChild(window.footer, "nav." + action)
            verify(button.visible, action + " must be visible inside the real tablet")
            var top = button.mapToItem(window, 0, 0)
            var bottom = button.mapToItem(window, button.width, button.height)
            verify(top.x >= 0 && bottom.x <= window.width)
            verify(top.y >= 0 && bottom.y <= window.height)
            verify(bottom.y - top.y >= 48)
            var pageBottom = loader.item.mapToItem(window, 0, loader.item.height).y
            verify(pageBottom <= top.y, "Places must not cover the navigation")
        })
    }

    function test_homePlacesNavigation_data() {
        return [
            {tag: "ipad-portrait", w: 768, h: 900, scale: 1},
            {tag: "ipad-landscape", w: 1024, h: 700, scale: 1},
            {tag: "compact-touch", w: 360, h: 640, scale: 1},
            {tag: "scaled-touch", w: 1080, h: 900, scale: 2.5}
        ]
    }
    function test_homePlacesNavigation(data) {
        var window = createTemporaryObject(windowFactory, testCase)
        verify(window !== null)
        currentWindow = window
        var profile = findChild(window, "tabletTouchProfile")
        verify(profile !== null)
        profile.directTouch = true
        profile.screenSpaceOriginAtSafeArea = true
        profile.surfaceWidth = data.w
        profile.surfaceHeight = data.h
        profile.safeInsetBottom = 20
        profile.screenSpaceContentScale = data.scale
        var loader = findChild(window, "loader")
        window.setScreenSpaceMode(true)
        window.loadSource(homeSource)
        window.setShown(true)
        waitForRendering(window)
        verify(!window.footer.visible)
        compare(window.footer.height, 0)

        window.loadSource(placesSource)
        tryVerify(function() { return window.footer.visible && window.footer.height > 0 })
        compare(loader.item.semanticScreenId, "places.home")
        loader.item.fromScript({channel: "com.overte.places", action: "PLACE_DATA", data: []})
        verify(!loader.item.loading)
        verifyNavigation(window, loader)
        // Real container resizing must keep the footer above native IME/safe area.
        profile.imeInsetBottom = 240
        tryCompare(window, "height", data.h - 240)
        verifyNavigation(window, loader)
        profile.imeInsetBottom = 0
        profile.surfaceWidth = data.h
        profile.surfaceHeight = data.w
        tryCompare(window, "width", data.h)
        tryCompare(window, "height", data.w - 20)
        verifyNavigation(window, loader)
        profile.surfaceWidth = data.w
        profile.surfaceHeight = data.h
        tryCompare(window, "height", data.h - 20)
        tryCompare(window, "opacity", 1)
        var home = findChild(window.footer, "nav.home")
        mouseClick(home, home.width / 2, home.height / 2)
        compare(proxy.homes, 1)
        compare(loader.source, homeSource)
        compare(window.footer.height, 0)

        window.loadSource(placesSource)
        tryVerify(function() { return window.footer.visible })
        var back = findChild(window.footer, "nav.back")
        mouseClick(back, back.width / 2, back.height / 2)
        compare(loader.source, homeSource)

        window.loadSource(placesSource)
        tryVerify(function() { return window.footer.visible })
        var close = findChild(window.footer, "nav.close")
        mouseClick(close, close.width / 2, close.height / 2)
        compare(proxy.closes, 1)
        verify(!window.shown)
        window.setShown(true)
        tryVerify(function() { return window.footer.visible })
        tryCompare(window, "opacity", 1)
        verifyNavigation(window, loader)
        window.loadSource("broken.qml")
        verify(loader.loadFailed)
        verify(window.footer.visible)
        mouseClick(home, home.width / 2, home.height / 2)
        compare(loader.source, homeSource)
        compare(window.footer.height, 0)
    }
}
