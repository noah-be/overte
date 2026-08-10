pragma Singleton
import QtQuick 2.12

QtObject {
    property int hideAddressBarCount: 0

    function hideAddressBar() {
        hideAddressBarCount += 1
    }

    function reset() {
        hideAddressBarCount = 0
    }
}
