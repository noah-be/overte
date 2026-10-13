// Native OS boundary fixture; the surrounding QML is copied unchanged.
import QtQuick 2.7
Item {
    id: root
    objectName: "FakeEmbeddedWebBackend"
    property string url: ""
    property string scriptUrl: ""
    property string userAgent: ""
    property bool useBackground: true
    property string eventBridgeJavaScript: ""
    property string sourceIdentity: ""
    property string surface: "world-entity"
    property string currentUrl: url
    property bool loading: false
    property bool canGoBack: true
    property bool canGoForward: true
    property string error: ""
    property bool bridgeAvailable: false
    property var initial: ({})
    property var events: []
    property var operations: []
    signal webEventReceived(var message)
    signal nativeClosed()
    function emitScriptEvent(message) { events.push(message); }
    function runJavaScript(source, callback) {
        operations.push("javascript");
        if (callback) { callback("native-result"); }
    }
    function openNative() { operations.push("open"); }
    function goBack() { operations.push("back"); }
    function goForward() { operations.push("forward"); }
    function reload() { operations.push("reload"); }
    function reloadAndBypassCache() { operations.push("bypass"); }
    function stop() { operations.push("stop"); }
    function unfocus() { operations.push("unfocus"); }
    Component.onCompleted: {
        initial = { url: url, scriptUrl: scriptUrl, userAgent: userAgent,
                    sourceIdentity: sourceIdentity, surface: surface,
                    eventBridgeJavaScript: eventBridgeJavaScript };
    }
}
