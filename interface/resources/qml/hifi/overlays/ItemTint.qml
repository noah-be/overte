// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.5
import QtQuick.Window 2.2

// Capture visible source content in memory, including AnimatedImage frames.
Canvas {
    id: root
    property Item source
    readonly property var captureWindow: source ? source.Window.window : null
    property color color: "transparent"
    property var snapshot
    property url captured
    property int generation: 0
    property bool busy: false
    property bool dirty: false
    renderTarget: Canvas.Image

    function clearCapture() {
        if (captured.toString() !== "") unloadImage(captured)
        captured = ""
        snapshot = null
        followupPaint = false
        requestPaint()
    }
    function refresh(invalidate) {
        if (invalidate) {
            generation++
            clearCapture()
        }
        dirty = true
        if (available && captureWindow && captureWindow.visible && visible && source && source.visible && source.width > 0 && source.height > 0)
            captureTimer.restart()
    }
    function captureFrame() {
        if (busy || !dirty || !available || !captureWindow || !captureWindow.visible || !source || !source.visible || !visible || source.width <= 0 || source.height <= 0) return
        dirty = false
        busy = true
        var ticket = generation
        var item = source
        var started = item.grabToImage(function(result) {
            busy = false
            if (ticket === generation && item === source && visible && captureWindow && captureWindow.visible) {
                clearCapture()
                snapshot = result
                captured = result.url
                loadImage(captured)
                followupPaint = true
                requestPaint()
            }
            if (dirty) captureTimer.restart()
        })
        if (!started) busy = false
    }
    Timer { id: captureTimer; interval: 0; onTriggered: root.captureFrame() }
    // Canvas.Image can lose its first painted texture after a zero-size resize.
    // One completion-driven repaint presents the retained capture; no polling.
    property bool followupPaint: false
    Timer { id: paintTimer; interval: 0; onTriggered: root.requestPaint() }
    onPainted: {
        if (followupPaint) {
            followupPaint = false
            paintTimer.restart()
        }
    }
    onSourceChanged: refresh(true)
    onCaptureWindowChanged: refresh(true)
    onAvailableChanged: refresh(true)
    onVisibleChanged: refresh(true)
    onWidthChanged: refresh(true)
    onHeightChanged: refresh(true)
    onColorChanged: requestPaint()
    onImageLoaded: requestPaint()
    Connections {
        target: root.captureWindow
        function onVisibleChanged() { root.refresh(true) }
    }
    Connections {
        target: root.source
        ignoreUnknownSignals: true
        function onCurrentFrameChanged() { root.refresh(false) }
        function onSourceChanged() { root.refresh(true) }
        function onStatusChanged() { root.refresh(true) }
        function onWidthChanged() { root.refresh(true) }
        function onHeightChanged() { root.refresh(true) }
        function onVisibleChanged() { root.refresh(true) }
    }
    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        if (captured.toString() === "" || !isImageLoaded(captured) || width <= 0 || height <= 0) return
        ctx.drawImage(captured, 0, 0, width, height)
        ctx.globalCompositeOperation = "source-in"
        ctx.fillStyle = color
        ctx.fillRect(0, 0, width, height)
    }
}
