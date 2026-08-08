import QtQuick 2.15

QtObject {
    // WindowRoot applies the shared Android tablet-app scale. Keeping Settings
    // neutral here prevents the two presentation layers compounding.
    readonly property real contentScale: 1.0
    // The phone has touchscreen controls, not the desktop/VR controller graph.
    readonly property bool showControllerSettings: false
    // Pico render scale changes are specific to the separate VR client.
    readonly property bool showPicoResolutionSettings: false
}
