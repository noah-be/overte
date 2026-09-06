import QtQuick 2.5

Item {
    id: root
    property alias border: borderRectangle.border
    property alias source: image.source
    property alias fillMode: image.fillMode
    property size sourceSize: Qt.size(-1, -1)
    property alias mipmap: image.mipmap
    property alias smooth: image.smooth
    property alias radius: borderRectangle.radius
    property alias status: image.status
    property alias progress: image.progress
    onRadiusChanged: drawing.requestPaint()
    property int captureGeneration: 0
    property bool captureBusy: false
    property bool captureAgain: false
    onSourceSizeChanged: synchronizeImage()
    onVisibleChanged: synchronizeImage()
    function synchronizeImage() {
        if (!drawing) return
        captureGeneration++
        if (drawing.cachedSource.toString() !== "") drawing.unloadImage(drawing.cachedSource)
        drawing.cachedSource = ""
        drawing.snapshot = null
        drawing.requestPaint()
        captureAgain = true
        refresh.restart()
    }
    Timer { id: refresh; interval: 0; onTriggered: root.refreshImage() }
    function refreshImage() {
        if (captureBusy || !drawing.available || !visible || image.status !== Image.Ready || image.width <= 0 || image.height <= 0) return
        captureAgain = false
        captureBusy = true
        var ticket = captureGeneration
        var started = image.grabToImage(function(result) {
            captureBusy = false
            if (ticket === captureGeneration && image.status === Image.Ready && root.visible) {
                drawing.snapshot = result
                drawing.cachedSource = result.url
                drawing.loadImage(result.url)
                drawing.requestPaint()
            }
            if (captureAgain) refresh.restart()
        })
        if (!started) captureBusy = false
    }

    // Keep sourceSize/cache/status in Qt Image. A transparent, naturally-sized
    // item provides its decoded pixels through the public in-memory capture API.

    Image {
        id: image
        opacity: 0
        width: implicitWidth
        height: implicitHeight
        sourceSize: root.sourceSize
        onSourceChanged: root.synchronizeImage()
        onStatusChanged: root.synchronizeImage()
        onFillModeChanged: drawing.requestPaint()
        onSourceSizeChanged: root.synchronizeImage()
        onSmoothChanged: drawing.requestPaint()
        onImplicitWidthChanged: root.synchronizeImage()
        onImplicitHeightChanged: root.synchronizeImage()
    }

    Canvas {
        id: drawing
        property url cachedSource
        property var snapshot
        anchors.fill: parent
        anchors.margins: borderRectangle.border.width
        renderTarget: Canvas.Image
        smooth: image.smooth
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onAvailableChanged: if (available) root.synchronizeImage()
        onImageLoaded: requestPaint()
        onVisibleChanged: if (visible) requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            if (image.status !== Image.Ready || !isImageLoaded(cachedSource) || width <= 0 || height <= 0) return
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
                        ctx.drawImage(cachedSource, x, y, tw, th)
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
                ctx.drawImage(cachedSource, (width - dw) / 2, (height - dh) / 2, dw, dh)
            }
        }
    }

    Rectangle {
        id: borderRectangle
        anchors.fill: parent
        color: "transparent"
    }
}
