import QtQuick 2.5
import Overte.Pico 1.0

Item {
    id: root
    anchors.fill: parent
    property string url: ""
    property string scriptUrl: ""
    property bool useBackground: true
    property string userAgent: ""

    onUrlChanged: load(root.url, root.scriptUrl, root.useBackground, root.userAgent)
    onScriptUrlChanged: {
        if (loader.item && root.webViewLoaded) {
            loader.item.scriptUrl = root.scriptUrl;
        } else if (!loader.item) {
            load(root.url, root.scriptUrl, root.useBackground, root.userAgent);
        }
    }
    onUseBackgroundChanged: {
        if (loader.item && root.webViewLoaded) {
            loader.item.useBackground = root.useBackground;
        } else if (!loader.item) {
            load(root.url, root.scriptUrl, root.useBackground, root.userAgent);
        }
    }
    onUserAgentChanged: {
        if (loader.item && root.webViewLoaded) {
            loader.item.userAgent = root.userAgent;
        } else if (!loader.item) {
            load(root.url, root.scriptUrl, root.useBackground, root.userAgent);
        }
    }

    readonly property var item: loader.item ? loader.item.webItem : null
    signal editorStateChanged()
    property bool webViewLoaded: false

    function fromScript(message) {
        if (loader.item && loader.item.fromScript) {
            loader.item.fromScript(message);
        }
    }

    Loader { id: loader; anchors.fill: parent }

    function load(url, scriptUrl, useBackground, userAgent) {
        if (loader.item && root.webViewLoaded) {
            loader.item.url = "about:blank";
        }
        if (url.match(/\.qml$/)) {
            root.webViewLoaded = false;
            loader.sourceComponent = undefined;
            loader.setSource(url);
        } else {
            root.webViewLoaded = true;
            loader.setSource("");
            loader.sourceComponent = picoWebSurface;
        }
    }

    Component {
        id: picoWebSurface
        Item {
            Canvas {
                id: webCanvas
                anchors.fill: parent
                enabled: false
                property string frameSource: ""
                property string previousSource: ""
                function discardFrame() {
                    if (frameSource !== "") unloadImage(frameSource);
                    if (previousSource !== "" && previousSource !== frameSource) unloadImage(previousSource);
                    frameSource = "";
                    previousSource = "";
                    requestPaint();
                }
                onImageLoaded: { if (webView.rendering && frameSource !== "") requestPaint(); }
                onPaint: {
                    var context = getContext("2d");
                    context.clearRect(0, 0, width, height);
                    if (webView.rendering && frameSource !== "" && isImageLoaded(frameSource)) {
                        context.drawImage(frameSource, 0, 0, width, height);
                    }
                }
                onPainted: {
                    if (previousSource !== "" && previousSource !== frameSource) {
                        unloadImage(previousSource);
                    }
                    previousSource = frameSource;
                    if (webView.rendering) refreshTimer.restart();
                }
            }
            Timer {
                id: refreshTimer
                interval: 100
                repeat: false
                running: webView.rendering
                onTriggered: {
                    var nextSource = webView.frameSource;
                    if (nextSource === "") {
                        restart();
                    } else {
                        webCanvas.frameSource = nextSource;
                        webCanvas.loadImage(nextSource);
                    }
                }
            }
            PicoWebView {
                id: webView
                anchors.fill: parent
                url: root.url
                scriptUrl: root.scriptUrl
                useBackground: root.useBackground
                userAgent: root.userAgent
                onRenderingChanged: {
                    if (!rendering) {
                        refreshTimer.stop();
                        webCanvas.discardFrame();
                    } else {
                        refreshTimer.restart();
                    }
                }
            }
            property alias webItem: webView
            Connections {
                target: webView
                function onEditorStateChanged() { root.editorStateChanged(); }
            }
            property alias url: webView.url
            property alias scriptUrl: webView.scriptUrl
            property alias useBackground: webView.useBackground
            property alias userAgent: webView.userAgent
            function destroy() { }
        }
    }

    Component.onCompleted: load(root.url, root.scriptUrl, root.useBackground, root.userAgent)
    signal sendToScript(var message)
}
