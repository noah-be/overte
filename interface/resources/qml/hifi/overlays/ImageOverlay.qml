import QtQuick 2.3

import "."

Overlay {
    id: root

    AnimatedImage {
        id: image
        // Zero extent means the remaining image, including after source replacement.
        property real xStart: 0
        property real yStart: 0
        property real xSize: 0
        property real ySize: 0
        onSourceSizeChanged: root.recalculateMargins()
        onStatusChanged: root.recalculateMargins()

        anchors.fill: parent
    }

    onWidthChanged: recalculateMargins()
    onHeightChanged: recalculateMargins()

    function recalculateMargins() {
        if (!image) { return; }
        var sourceWidth = image.sourceSize.width;
        var sourceHeight = image.sourceSize.height;
        var cropWidth = image.xSize === 0 ? sourceWidth - image.xStart : image.xSize;
        var cropHeight = image.ySize === 0 ? sourceHeight - image.yStart : image.ySize;
        if (image.status !== Image.Ready || sourceWidth <= 0 || sourceHeight <= 0 ||
                !isFinite(cropWidth) || !isFinite(cropHeight) || cropWidth <= 0 || cropHeight <= 0 ||
                !isFinite(image.xStart) || !isFinite(image.yStart)) {
            image.anchors.leftMargin = 0;
            image.anchors.topMargin = 0;
            image.anchors.rightMargin = 0;
            image.anchors.bottomMargin = 0;
            return;
        }
        image.anchors.leftMargin = -image.xStart * root.width / cropWidth;
        image.anchors.topMargin = -image.yStart * root.height / cropHeight;
        image.anchors.rightMargin = (image.xStart + cropWidth - sourceWidth) * root.width / cropWidth;
        image.anchors.bottomMargin = (image.yStart + cropHeight - sourceHeight) * root.height / cropHeight;
    }

    ItemTint {
        id: color
        anchors.fill: image
        source: image
    }

    function updateSubImage(subImage) {
        var keys = Object.keys(subImage);
        for (var i = 0; i < keys.length; ++i) {
            var key = keys[i];
            var value = subImage[key];
            switch (key) {
                case "x": image.xStart = value; break;
                case "y": image.yStart = value; break;
                case "width": image.xSize = value; break;
                case "height": image.ySize = value; break;
            }
        }
        recalculateMargins();
    }

    function updatePropertiesFromScript(properties) {
        var keys = Object.keys(properties);
        for (var i = 0; i < keys.length; ++i) {
            var key = keys[i];
            var value = properties[key];
            switch (key) {
                case "height": root.height = value; break;
                case "width": root.width = value; break;
                case "x": root.x = value; break;
                case "y": root.y = value; break;
                case "visible": root.visible = value; break;
                case "alpha": root.opacity = value; break;
                case "imageURL": image.source = value; break;
                case "subImage": updateSubImage(value); break;
                case "color": color.color = Qt.rgba(value.red / 255, value.green / 255, value.blue / 255, root.opacity); break;
                case "bounds": break; // The bounds property is handled in C++.
                default: console.log("OVERLAY Unhandled image property " + key);
            }
        }
    }
}

