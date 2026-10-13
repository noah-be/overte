// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtTest 1.2
import "../controls"
import ".." as World

Item {
    width: 480
    height: 640
    QtObject {
        id: eventBridge
        property var received: []
        signal scriptEventReceived(var message)
        function emitWebEvent(message) { received.push(message); }
    }
    QtObject {
        id: tabletRoot
        property int returned: 0
        function returnToPreviousApp() { returned++; }
    }
    Component { id: webComponent; EmbeddedWebView { width: 480; height: 640 } }
    Component { id: tabletComponent; NativeFlickableWebViewCore { width: 480; height: 640 } }
    Component { id: worldComponent; World.Web3DSurface { width: 480; height: 640 } }
    Component { id: screenComponent; TabletWebScreen { width: 480; height: 640 } }
    Component { id: windowComponent; TabletWebView { width: 480; height: 640 } }
    SignalSpy { id: webEvents; signalName: "webEventReceived" }
    SignalSpy { id: nativeClosed; signalName: "nativeClosed" }
    SignalSpy { id: scriptMessages; signalName: "sendToScript" }
    TestCase {
        name: "EmbeddedWebCallers"
        when: windowShown
        function create(component, properties) {
            var item = createTemporaryObject(component, parent, properties);
            verify(item !== null);
            return item;
        }
        function init() { eventBridge.received = []; webEvents.clear(); nativeClosed.clear(); scriptMessages.clear(); }
        function test_providerWarningReservesSpaceAndPreservesDocument() {
            var web = create(webComponent, { url: "https://example.test" });
            tryVerify(function() { return web.backend !== null; });
            var banner = findChild(web, "EmbeddedWebWarning");
            var fatal = findChild(web, "EmbeddedWebError");
            web.backend.warning = "Document is available; native bridge provider needs updating.";
            tryVerify(function() { return banner.visible && banner.height > 0; });
            verify(!fatal.visible);
            compare(web.error, "");
            verify(web.backend.visible && web.backend.height > 0);
            tryCompare(findChild(web, "EmbeddedWebDocument"), "y", banner.height);
            var result = "";
            web.runJavaScript("document.title", function(value) { result = value; });
            compare(result, "native-result");
            web.backend.warning = "";
            tryCompare(findChild(web, "EmbeddedWebDocument"), "y", 0);
        }
        function test_fatalErrorRetainsVisibleFailureSurface() {
            var web = create(webComponent, { url: "https://example.test" });
            tryVerify(function() { return web.backend !== null; });
            web.backend.warning = "Provider warning";
            web.backend.error = "The native document failed to load.";
            verify(findChild(web, "EmbeddedWebError").visible);
            verify(!findChild(web, "EmbeddedWebWarning").visible);
        }
        function test_configureBeforeNavigationAndUpdate() {
            var web = create(webComponent, { url: "https://example.test/start", scriptUrl: "https://example.test/client.js",
                sourceIdentity: "entity-one", userAgent: "Overte test", surface: "world-entity", eventBridgeJavaScript: "real-bootstrap" });
            tryVerify(function() { return web.backend !== null; });
            compare(web.backend.initial.url, "https://example.test/start");
            compare(web.backend.initial.scriptUrl, "https://example.test/client.js");
            compare(web.backend.initial.sourceIdentity, "entity-one");
            compare(web.backend.initial.surface, "world-entity");
            compare(web.backend.initial.eventBridgeJavaScript, "real-bootstrap");
            web.scriptUrl = "https://example.test/next.js";
            compare(web.backend.scriptUrl, web.scriptUrl);
            web.backend.currentUrl = "https://different.test/redirect";
            compare(web.currentUrl, "https://different.test/redirect");
            compare(web.url, "https://example.test/start");
        }
        function test_firstEventBeforeIdleAndSingleBidirectionalRelay() {
            var web = create(webComponent, { url: "https://example.test" });
            tryVerify(function() { return web.backend !== null; });
            webEvents.target = web;
            compare(web.bridgeAvailable, false);
            web.backend.webEventReceived({ first: true });
            compare(eventBridge.received.length, 1);
            compare(eventBridge.received[0].first, true);
            compare(webEvents.count, 1);
            eventBridge.scriptEventReceived({ reply: "first" });
            compare(web.backend.events.length, 1);
            compare(web.backend.events[0].reply, "first");
            web.visible = false;
            web.backend.webEventReceived("hidden");
            eventBridge.scriptEventReceived("hidden");
            compare(eventBridge.received.length, 1);
            compare(webEvents.count, 1);
            compare(web.backend.events.length, 1);
            web.visible = true;
            web.enabled = false;
            eventBridge.scriptEventReceived("disabled");
            compare(web.backend.events.length, 1);
        }
        function test_tabletCommandsAndKeyboardPreserveDocument() {
            var tablet = create(tabletComponent, { url: "https://example.test" });
            var web = tablet.webViewCore;
            tryVerify(function() { return web.backend !== null; });
            compare(web.backend.surface, "tablet");
            tablet.stopUnfocus();
            compare(web.backend.operations.length, 1);
            compare(web.backend.operations[0], "unfocus");
            web.goBack(); web.goForward(); web.reload(); web.reloadAndBypassCache();
            compare(web.backend.operations.slice(1).join(","), "back,forward,reload,bypass");
            var result = "";
            web.runJavaScript("document.title", function(value) { result = value; });
            compare(result, "native-result");
            nativeClosed.target = tablet;
            web.backend.nativeClosed();
            compare(nativeClosed.count, 1);
            mouseClick(findChild(tablet, "EmbeddedWebBack"));
            mouseClick(findChild(tablet, "EmbeddedWebForward"));
            mouseClick(findChild(tablet, "EmbeddedWebReload"));
            compare(web.backend.operations.slice(-3).join(","), "back,forward,reload");
            tablet.stop();
            compare(web.backend.operations[web.backend.operations.length - 1], "stop");
        }
        function test_actualTabletScreensAcceptScriptsAndPreserveKeyboard() {
            var screen = create(screenComponent, { url: "https://example.test/tablet", scriptURL: "https://example.test/client.js" });
            var nativeView = findChild(screen, "FakeEmbeddedWebBackend");
            verify(nativeView !== null);
            compare(nativeView.scriptUrl, screen.scriptURL);
            screen.keyboardRaised = true;
            compare(nativeView.operations[nativeView.operations.length - 1], "unfocus");
            nativeView.nativeClosed();
            compare(tabletRoot.returned, 1);

            var browser = create(windowComponent, { url: "https://example.test/window", scriptURL: "https://example.test/window.js" });
            nativeView = findChild(browser, "FakeEmbeddedWebBackend");
            verify(nativeView !== null);
            compare(nativeView.scriptUrl, browser.scriptURL);
            browser.keyboardRaised = true;
            compare(nativeView.operations[nativeView.operations.length - 1], "unfocus");
            browser.goBack(); browser.goForward(); browser.reloadPage();
            compare(nativeView.operations.slice(-3).join(","), "back,forward,bypass");
            compare(browser.history[0], "https://example.test/window");
            nativeView.nativeClosed();
            compare(browser.visible, false);
        }
        function test_worldQmlMessagesSurviveSourceReplacement() {
            var world = create(worldComponent, { url: Qt.resolvedUrl("FakeDocument.qml").toString() });
            tryVerify(function() { return world.item !== null; });
            scriptMessages.target = world;
            world.fromScript({ intoQml: 1 });
            compare(world.item.messages.length, 1);
            world.item.sendToScript({ intoScript: 1 });
            compare(scriptMessages.count, 1);
            world.url = Qt.resolvedUrl("FakeDocument.qml").toString() + "?next=1";
            tryVerify(function() { return world.item !== null; });
            world.item.sendToScript({ intoScript: 2 });
            compare(scriptMessages.count, 2);
        }
        function test_worldHtmlAndClearSourceReleaseBackend() {
            var world = create(worldComponent, { url: "https://example.test/entity" });
            tryVerify(function() { return world.item !== null && world.item.backend !== null; });
            compare(world.item.backend.surface, "world-entity");
            compare(world.item.backend.url, "https://example.test/entity");
            world.scriptUrl = "https://example.test/script.js";
            compare(world.item.backend.scriptUrl, world.scriptUrl);
            world.url = Qt.resolvedUrl("FakeDocument.qml").toString();
            tryVerify(function() { return world.item !== null && typeof world.item.messages !== "undefined"; });
            var web = create(webComponent, { url: "https://example.test" });
            tryVerify(function() { return web.backend !== null; });
            web.url = "";
            tryCompare(web, "backend", null);
        }
    }
}
