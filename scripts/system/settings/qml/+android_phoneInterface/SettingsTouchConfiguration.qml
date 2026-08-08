import QtQuick 2.15

QtObject {
    // WindowRoot applies the shared Android tablet-app scale. Keeping Settings
    // neutral here prevents the two presentation layers compounding.
    readonly property real contentScale: 1.0
}
