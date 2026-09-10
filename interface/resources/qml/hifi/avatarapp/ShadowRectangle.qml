import stylesUit 1.0
import QtQuick 2.9
import "../../controls" as CpuControls

Item {
    id: root
    property alias color: rectangle.color
    // Qt Rectangle.gradient itself has no notify signal. Keep the wrapper
    // property reactive so replacing a gradient also refreshes the shadow.
    property var gradient: undefined
    property alias border: rectangle.border
    property alias radius: rectangle.radius
    property alias dropShadowRadius: shadow.radius
    property alias dropShadowHorizontalOffset: shadow.horizontalOffset
    property alias dropShadowVerticalOffset: shadow.verticalOffset
    property alias dropShadowOpacity: shadow.opacity

    CpuControls.CpuDropShadow {
        id: shadow
        anchors.fill: rectangle
        radius: 6
        horizontalOffset: 0
        verticalOffset: 3
        color: Qt.rgba(0, 0, 0, 0.25)
        source: rectangle
        sourceGradient: root.gradient
    }

    Rectangle {
        id: rectangle
        gradient: root.gradient
        width: parent.width
        height: parent.height
    }


}
