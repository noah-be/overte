// Qt Quick Controls 2 adapter for the shared tablet menu model.
import QtQuick.Controls 2.3

Menu {
    id: wrappedMenu
    objectName: "wrappedMenu"
    readonly property int type: 2
    // Popup visibility is unrelated to visibility in the tablet projection.
    property bool tabletVisible: true
    readonly property var items: {
        var result = []
        for (var i = 0; i < count; ++i) {
            var entry = itemAt(i)
            result.push(entry.subMenu ? entry.subMenu : entry)
        }
        return result
    }

    function addMenuWrap(menu) { addMenu(menu) }
    function addItemWrap(item) { addItem(item) }
    function insertItemWrap(before, item) {
        for (var i = 0; i < count; ++i) {
            if (itemAt(i) === before) {
                insertItem(i, item)
                return true
            }
        }
        return false
    }
}
