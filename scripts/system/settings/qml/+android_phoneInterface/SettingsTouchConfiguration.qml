import QtQuick 2.15

QtObject {
    // Desktop-sized 60 px rows are too small on a dense phone touchscreen.
    // Scaling the complete logical Settings surface also scales hit targets
    // while retaining its existing layout and navigation behavior.
    readonly property real contentScale: 1.5
}
