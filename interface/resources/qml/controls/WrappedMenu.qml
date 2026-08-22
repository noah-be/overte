import QtQuick.Controls 2.3

Menu {
    id: wrappedMenu
    objectName: "wrappedMenu"

    function addMenuWrap(menu) {
        return addMenu(menu)
    }

    function addItemWrap(item) {
        addItem(item)
    }
}
