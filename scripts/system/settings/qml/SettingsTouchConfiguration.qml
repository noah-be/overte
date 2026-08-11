import QtQuick 2.15

QtObject {
    readonly property real contentScale: 1.0
    readonly property bool showGraphicsSettings: true
    readonly property bool showControllerSettings: true
    readonly property bool showPicoResolutionSettings: true
    // Product-specific pages fail closed unless an immutable QFileSelector
    // profile for the compiled Android target explicitly enables them.
    readonly property bool showPicoInteractionSettings: false
}
