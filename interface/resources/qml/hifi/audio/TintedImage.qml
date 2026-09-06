// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.5

// Alpha-preserving CPU tinting for software and GPU Qt Quick backends.
Canvas {
    property url source
    property color color: "white"
    property url loadedSource
    renderTarget: Canvas.Image
    onSourceChanged: {
        if (loadedSource.toString() !== "") unloadImage(loadedSource)
        loadedSource = source
        if (source.toString() !== "") loadImage(source)
        requestPaint()
    }
    onAvailableChanged: {
        if (available) {
            if (source.toString() !== "" && !isImageLoaded(source)) loadImage(source)
            requestPaint()
        }
    }
    onVisibleChanged: if (visible) requestPaint()
    onImageLoaded: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    function paintTint(ctx) {
        ctx.fillStyle = color
        ctx.fillRect(0, 0, width, height)
    }
    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        if (width <= 0 || height <= 0 || source.toString() === "" || !isImageLoaded(source)) return
        ctx.drawImage(source, 0, 0, width, height)
        ctx.globalCompositeOperation = "source-in"
        paintTint(ctx)
    }
}
