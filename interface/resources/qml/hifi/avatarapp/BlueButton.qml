import QtQuick 2.5
import stylesUit 1.0
import controlsUit 1.0 as HifiControlsUit

HifiControlsUit.Button {
    HifiConstants {
        id: hifi
    }

    width: Math.max(hifi.dimensions.buttonWidth, implicitTextWidth + 20)
    HifiControlsUit.TouchUiMetrics { id: touchMetrics }
    fontSize: Math.round(18 * touchMetrics.textScale)
    color: hifi.buttons.blue;
    colorScheme: hifi.colorSchemes.light;
    height: Math.max(40, touchMetrics.adaptiveMinimumControlHeight)
}
