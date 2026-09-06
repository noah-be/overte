// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.5

// CPU image drawing also works with the Qt Quick software adaptation.
Canvas {
    id: meter
    property real level: 0
    property bool vertical: false
    property color gutter: "#575757"
    property color low: "#39A38F"
    property color middle: "#1FC6A6"
    property color high: "#C0C000"
    renderTarget: Canvas.Image
    onLevelChanged: requestPaint()
    onVerticalChanged: requestPaint()
    onGutterChanged: requestPaint()
    onLowChanged: requestPaint()
    onMiddleChanged: requestPaint()
    onHighChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        if (width <= 0 || height <= 0) return
        var fraction = isFinite(level) ? Math.max(0, Math.min(1, level)) : 0
        var radius = Math.min(4, width / 2, height / 2)
        ctx.beginPath()
        ctx.roundedRect(0, 0, width, height, radius, radius)
        ctx.fillStyle = gutter
        ctx.fill()
        if (fraction <= 0) return
        var filledWidth = vertical ? width : width * fraction
        var filledHeight = vertical ? height * fraction : height
        var y = vertical ? height - filledHeight : 0
        var fillRadius = Math.min(radius, filledWidth / 2, filledHeight / 2)
        var gradient = vertical ? ctx.createLinearGradient(0, height, 0, 0)
                                : ctx.createLinearGradient(0, 0, width, 0)
        gradient.addColorStop(0, low)
        gradient.addColorStop(0.5, middle)
        gradient.addColorStop(1, high)
        ctx.beginPath()
        ctx.roundedRect(0, y, filledWidth, filledHeight, fillRadius, fillRadius)
        ctx.fillStyle = gradient
        ctx.fill()
    }
}
