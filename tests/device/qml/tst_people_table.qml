import QtQuick 2.12
import QtTest 1.2
import "../../../interface/resources/qml/hifi" as People

TestCase {
    id: testCase
    name: "PeopleTable"
    when: windowShown
    visible: true
    width: 640
    height: 480

    Component {
        id: tableComponent
        People.PeopleTable {
            width: 600
            height: 300
            headerVisible: true
            sortIndicatorVisible: true
            People.PeopleTableColumn { role: "name"; title: "Name"; width: 300 }
            People.PeopleTableColumn { role: "gain"; title: "Gain"; width: 100 }
            model: ListModel {
                ListElement { name: "Alice"; gain: 1 }
                ListElement { name: "Bob"; gain: 2 }
            }
            rowDelegate: Rectangle {
                height: styleData.selected ? 80 : 60
                color: styleData.selected ? "blue" : "white"
            }
            itemDelegate: Text {
                objectName: "cell-" + styleData.row + "-" + styleData.column
                text: styleData.value
            }
        }
    }

    function test_modelsCellsAndSelection() {
        var table = createTemporaryObject(tableComponent, testCase)
        verify(table !== null)
        compare(table.rowCount, 2)
        tryVerify(function() { return findChild(table, "cell-0-0") !== null })
        compare(findChild(table, "cell-0-0").text, "Alice")
        compare(findChild(table, "cell-1-1").text, "2")
        table.selection.select([0, 1])
        verify(table.selection.contains(0))
        table.selection.deselect(0)
        var selected = []
        table.selection.forEach(function(index) { selected.push(index) })
        compare(selected, [1])
        table.selection.clear()
        compare(table.selection.indexes, [])
        table.model.setProperty(0, "name", "Carol")
        tryCompare(findChild(table, "cell-0-0"), "text", "Carol")
    }

    function test_headerSortAndHiddenColumns() {
        var table = createTemporaryObject(tableComponent, testCase)
        verify(table !== null)
        mouseClick(table, 350, table.headerHeight / 2)
        compare(table.sortIndicatorColumn, 1)
        mouseClick(table, 350, table.headerHeight / 2)
        compare(table.sortIndicatorOrder, Qt.DescendingOrder)
        table.getColumn(1).visible = false
        tryVerify(function() { return !findChild(table, "cell-0-1") })
    }
}
