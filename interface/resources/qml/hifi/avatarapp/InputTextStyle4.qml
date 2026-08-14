import controlsUit 1.0 as HifiControlsUit
import stylesUit 1.0

import QtQuick 2.0
import QtQuick.Controls 2.2

HifiControlsUit.TextField {
    id: control
    HifiControlsUit.TouchUiMetrics { id: touchMetrics }
    font.family: "Fira Sans"
    font.pixelSize: Math.round(15 * touchMetrics.textScale);
    implicitHeight: Math.max(40, touchMetrics.adaptiveMinimumControlHeight)

    AvatarAppStyle {
        id: style
    }
}
