//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

import QtQuick 2.15
import QtWebView 1.1

Item {
    id: flick

    property alias url: bridge.url
    property alias canGoBack: bridge.canGoBack
    property alias webViewCore: bridge
    property bool useBackground: false
    property string userAgent: ""
    property string userScriptUrl: ""
    property string urlTag: "noDownload=false"
    property bool interactive: true
    property bool blurOnCtrlShift: true

    signal newViewRequestedCallback(var request)
    signal loadingChangedCallback(var loadRequest)

    function stop() {
        webView.stop();
    }

    function unfocus() {
        webView.focus = false;
    }

    function stopUnfocus() {
    }

    Item {
        id: bridge
        anchors.fill: parent
        property alias url: webView.url
        readonly property bool canGoBack: webView.canGoBack
        readonly property bool canGoForward: webView.canGoForward
        readonly property bool loading: webView.loading

        function goBack() {
            webView.goBack();
        }

        function goForward() {
            webView.goForward();
        }

        function reload() {
            webView.reload();
        }

        function reloadAndBypassCache() {
            // WKWebView owns its HTTP cache policy. A normal reload is the
            // closest supported operation exposed by Qt WebView.
            webView.reload();
        }

        function setActiveFocusOnPress(enabled) {
            if (!enabled) {
                webView.focus = false;
            }
        }

        function setEnabled(enabled) {
            webView.enabled = enabled;
        }

        function forceActiveFocus() {
            webView.forceActiveFocus();
        }

        WebView {
            id: webView
            anchors.fill: parent
            visible: flick.visible

            onLoadingChanged: function(loadRequest) {
                flick.loadingChangedCallback(loadRequest);
            }
        }
    }
}
