// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.5
import QtQuick.Window 2.2
import "CpuShadowPixels.js" as ShadowPixels

// Shadow-only CPU Canvas. Callers place this item before its visible source
// in sibling paint order. No shader, copied foreground or frame polling.
Item {
    id: root
    property Item source
    property var sourceGradient: source && source.gradient ? source.gradient : null
    readonly property Item observedSource: {
        for (var ancestor = root; ancestor; ancestor = ancestor.parent) {
            if (ancestor === source) return null
        }
        return source
    }
    property color color: "black"
    property real spread: 0
    property real radius: 4
    property real horizontalOffset: 0
    property real verticalOffset: 0
    readonly property var captureWindow: source ? source.Window.window : null
    property int generation: 0
    property bool busy: false
    property bool dirty: false
    property var snapshot
    property url captured
    property var pendingSnapshot
    property url pendingUrl
    property int pendingGeneration: 0
    readonly property real blur: isFinite(radius) ? Math.max(0, radius) : 0
    readonly property real offsetX: isFinite(horizontalOffset) ? horizontalOffset : 0
    readonly property real offsetY: isFinite(verticalOffset) ? verticalOffset : 0
    readonly property real padding: Math.ceil(2 * blur + Math.max(Math.abs(offsetX), Math.abs(offsetY)))

    function clearPending() {
        if (pendingUrl.toString() !== "" && pendingUrl !== captured) drawing.unloadImage(pendingUrl)
        pendingUrl = ""
        pendingSnapshot = null
    }
    function publishCapture() {
        if (!pendingSnapshot || pendingGeneration !== generation || !visible || !source || !source.visible ||
                !captureWindow || !captureWindow.visible || !drawing.isImageLoaded(pendingUrl)) return
        var previous = captured
        snapshot = pendingSnapshot
        captured = pendingUrl
        pendingSnapshot = null
        pendingUrl = ""
        if (previous.toString() !== "" && previous !== captured) drawing.unloadImage(previous)
        drawing.requestPaint()
    }
    function clearCapture() {
        clearPending()
        if (captured.toString() !== "") drawing.unloadImage(captured)
        captured = ""
        snapshot = null
        drawing.requestPaint()
    }
    function refresh(invalidate) {
        if (invalidate) {
            generation++
            clearCapture()
        }
        dirty = true
        captureTimer.restart()
    }
    function capture() {
        if (busy || !dirty || !drawing.available || !visible || !source || !source.visible ||
                !captureWindow || !captureWindow.visible || width <= 0 || height <= 0 ||
                source.width <= 0 || source.height <= 0) return
        // An ancestor source would include this effect and recurse forever.
        for (var ancestor = root; ancestor; ancestor = ancestor.parent) {
            if (ancestor === source) return
        }
        dirty = false
        busy = true
        var ticket = generation
        var item = source
        var started = item.grabToImage(function(result) {
            busy = false
            if (ticket === generation && source === item && visible && item.visible &&
                    captureWindow && captureWindow.visible) {
                clearPending()
                pendingSnapshot = result
                pendingUrl = result.url
                pendingGeneration = ticket
                drawing.loadImage(pendingUrl)
                publishCapture()
            }
            if (dirty) captureTimer.restart()
        })
        if (!started) busy = false
    }
    Timer { id: captureTimer; interval: 0; onTriggered: root.capture() }
    CpuShadowSourceObserver { source: root.observedSource; gradientSource: root.sourceGradient; onChanged: function(invalidate) { root.refresh(invalidate) } }
    Connections {
        target: root.captureWindow
        function onVisibleChanged() { root.refresh(true) }
    }
    onSourceChanged: refresh(true)
    onSourceGradientChanged: refresh(true)
    onCaptureWindowChanged: refresh(true)
    onVisibleChanged: refresh(true)
    onWidthChanged: refresh(false)
    onHeightChanged: refresh(false)
    onColorChanged: drawing.requestPaint()
    onRadiusChanged: drawing.requestPaint()
    onSpreadChanged: drawing.requestPaint()
    onHorizontalOffsetChanged: drawing.requestPaint()
    onVerticalOffsetChanged: drawing.requestPaint()
    Canvas {
        id: drawing
        x: -root.padding
        y: -root.padding
        width: root.width + 2 * root.padding
        height: root.height + 2 * root.padding
        renderTarget: Canvas.Image
        onAvailableChanged: root.refresh(true)
        onImageLoaded: root.publishCapture()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            if (!root.snapshot || !isImageLoaded(root.captured) || root.width <= 0 || root.height <= 0) return
            ctx.drawImage(root.captured, root.padding, root.padding, root.width, root.height)
            var pixels = ctx.getImageData(0, 0, width, height)
            ctx.clearRect(0, 0, width, height)
            ShadowPixels.paintShadow(ctx, pixels, root.blur, root.offsetX, root.offsetY, root.color, root.spread)
        }
    }
}
