// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.5

// Centered elliptical gradient drawn into a CPU image. A stop at 0.5 reaches
// the midpoints of the four edges, matching the Frame's documented geometry.
// Replace the stops array to update colors/positions; entries are value data.
Canvas {
    property var stops: []
    renderTarget: Canvas.Image
    onStopsChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onVisibleChanged: if (visible) requestPaint()
    onAvailableChanged: if (available) requestPaint()
    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        if (width <= 0 || height <= 0 || stops.length === 0) return
        ctx.scale(width, height)
        var fill = ctx.createRadialGradient(0.5, 0.5, 0, 0.5, 0.5, 1)
        for (var i = 0; i < stops.length; ++i) {
            fill.addColorStop(stops[i].position, stops[i].color)
        }
        ctx.fillStyle = fill
        ctx.fillRect(0, 0, 1, 1)
    }
}
