// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.5

// The full gradient is alpha-masked by the source; the unfilled top is grey.
TintedImage {
    property real level: 0
    property color gutter: "#b2b2b2"
    property color low: "#39A38F"
    property color middle: "#1FC6A6"
    property color high: "#C0C000"
    onLevelChanged: requestPaint()
    onGutterChanged: requestPaint()
    onLowChanged: requestPaint()
    onMiddleChanged: requestPaint()
    onHighChanged: requestPaint()
    function paintTint(ctx) {
        var gradient = ctx.createLinearGradient(0, height, 0, 0)
        gradient.addColorStop(0, low)
        gradient.addColorStop(0.5, middle)
        gradient.addColorStop(1, high)
        ctx.fillStyle = gradient
        ctx.fillRect(0, 0, width, height)
        var fraction = isFinite(level) ? Math.max(0, Math.min(1, level)) : 0
        ctx.globalCompositeOperation = "source-atop"
        ctx.fillStyle = gutter
        ctx.fillRect(0, 0, width, height * (1 - fraction))
    }
}
