import QtQuick 2.15

QtObject {
    readonly property real contentScale: 1.0
    readonly property bool showGraphicsSettings: true
    readonly property bool showControllerSettings: true
    readonly property bool showPicoResolutionSettings: false
    readonly property bool showPicoInteractionSettings: false

    function admitsSemanticControl(controlId) {
        return controlId === "settings.general" || controlId === "settings.audio"
            || controlId === "settings.security" || controlId === "settings.graphics"
            || controlId === "settings.controllers"
    }
}
