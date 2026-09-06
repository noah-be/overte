import QtQuick 2.5

Item {
    id: root
    property alias border: borderRectangle.border
    property alias source: image.source
    property alias fillMode: image.fillMode
    property alias radius: borderRectangle.radius
    property alias status: image.status
    property alias progress: image.progress
    onRadiusChanged: drawing.requestPaint()

    // Keep Qt's image loading/cache/status implementation. Canvas draws this
    // already loaded image directly, without another URL request or export.
    Image {
        id: image
        visible: false
        anchors.fill: parent
        anchors.margins: borderRectangle.border.width
        onSourceChanged: drawing.requestPaint()
        onStatusChanged: drawing.requestPaint()
        onFillModeChanged: drawing.requestPaint()
        onImplicitWidthChanged: drawing.requestPaint()
        onImplicitHeightChanged: drawing.requestPaint()
    }

    Canvas {
        id: drawing
        anchors.fill: image
        renderTarget: Canvas.Image
        smooth: true
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onAvailableChanged: if (available) requestPaint()
        onVisibleChanged: if (visible) requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            if (image.status !== Image.Ready || width <= 0 || height <= 0) return
            var sw = image.implicitWidth
            var sh = image.implicitHeight
            if (sw <= 0 || sh <= 0) return
            var r = isFinite(root.radius) ? Math.max(0, Math.min(root.radius, width / 2, height / 2)) : 0
            ctx.beginPath()
            ctx.roundedRect(0, 0, width, height, r, r)
            ctx.clip()
            var mode = image.fillMode
            if (mode === Image.Tile || mode === Image.TileHorizontally || mode === Image.TileVertically) {
                var tw = mode === Image.TileVertically ? width : sw
                var th = mode === Image.TileHorizontally ? height : sh
                // Qt Image centers its tile origin using the default alignment.
                var x0 = (width - tw) / 2
                var y0 = (height - th) / 2
                x0 -= Math.ceil(x0 / tw) * tw
                y0 -= Math.ceil(y0 / th) * th
                for (var y = y0; y < height; y += th)
                    for (var x = x0; x < width; x += tw)
                        ctx.drawImage(image, x, y, tw, th)
            } else {
                var dw = width
                var dh = height
                if (mode === Image.PreserveAspectFit || mode === Image.PreserveAspectCrop) {
                    var scale = mode === Image.PreserveAspectFit ? Math.min(width / sw, height / sh)
                                                               : Math.max(width / sw, height / sh)
                    dw = sw * scale
                    dh = sh * scale
                } else if (mode === Image.Pad) {
                    dw = sw
                    dh = sh
                }
                ctx.drawImage(image, (width - dw) / 2, (height - dh) / 2, dw, dh)
            }
        }
    }

    Rectangle {
        id: borderRectangle
        anchors.fill: parent
        color: "transparent"
    }
}
