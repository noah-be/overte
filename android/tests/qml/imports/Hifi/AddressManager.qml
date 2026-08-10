pragma Singleton
import QtQuick 2.12

QtObject {
    property string href: "hifi://initial"

    function reset() {
        href = "hifi://initial"
    }
}
