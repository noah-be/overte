import QtQuick 2.7
import QtQuick.Controls 2.3
import controlsUit 1.0 as HifiControls

// People retains its scripting model, sorting and cell actions. A virtualized
// ListView replaces the removed Controls 1 TableView on every platform.
Item {
    id: table
    default property list<PeopleTableColumn> columns
    property var model
    property Component itemDelegate
    property Component rowDelegate
    property bool centerHeaderText: false
    property bool sortIndicatorVisible: false
    property bool headerVisible: false
    property int sortIndicatorColumn: 0
    property int sortIndicatorOrder: Qt.AscendingOrder
    readonly property int rowCount: rows.count
    property alias flickableItem: rows
    property var titlePaintedPos: []
    signal titlePaintedPosSignal(int column)
    property QtObject metrics: HifiControls.TouchUiMetrics {}
    readonly property real headerHeight: headerVisible
        ? Math.max(32, metrics.adaptiveMinimumControlHeight) : 0

    function getColumn(index) { return columns[index] || null }
    function positionViewAtRow(index, mode) { rows.positionViewAtIndex(index, mode) }

    property QtObject selection: QtObject {
        property var indexes: []
        signal selectionChanged()
        function contains(index) { return indexes.indexOf(index) !== -1 }
        function clear() {
            if (indexes.length === 0) { return }
            indexes = []
            selectionChanged()
        }
        function select(first, last) {
            var added = Array.isArray(first) ? first : [first]
            if (last !== undefined) {
                added = []
                for (var i = first; i <= last; ++i) { added.push(i) }
            }
            var next = indexes.slice()
            added.forEach(function(index) {
                if (index >= 0 && index < table.rowCount && next.indexOf(index) === -1) {
                    next.push(index)
                }
            })
            if (next.length !== indexes.length) {
                indexes = next
                selectionChanged()
            }
        }
        function deselect(index) {
            if (!contains(index)) { return }
            indexes = indexes.filter(function(value) { return value !== index })
            selectionChanged()
        }
        function forEach(callback) { indexes.slice().forEach(callback) }
    }

    property Item header: Row {
        parent: table
        width: parent.width
        height: table.headerHeight
        visible: table.headerVisible
        Repeater {
            model: table.columns
            delegate: Rectangle {
                id: heading
                property var column: modelData
                width: column.visible ? Math.max(0, column.width) : 0
                height: table.headerHeight
                visible: column.visible
                color: "#e3e3e3"
                clip: true
                Text {
                    id: caption
                    anchors.fill: parent
                    anchors.margins: 4
                    text: heading.column.title + (table.sortIndicatorVisible &&
                        table.sortIndicatorColumn === index
                        ? (table.sortIndicatorOrder === Qt.AscendingOrder ? " ▴" : " ▾") : "")
                    elide: Text.ElideRight
                    horizontalAlignment: table.centerHeaderText ? Text.AlignHCenter : Text.AlignLeft
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: Math.round(14 * table.metrics.textScale)
                    onContentWidthChanged: {
                        table.titlePaintedPos[index] = caption.x + caption.contentWidth
                        table.titlePaintedPosSignal(index)
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: table.sortIndicatorVisible
                    onClicked: {
                        if (table.sortIndicatorColumn === index) {
                            table.sortIndicatorOrder = table.sortIndicatorOrder === Qt.AscendingOrder
                                ? Qt.DescendingOrder : Qt.AscendingOrder
                        } else {
                            table.sortIndicatorColumn = index
                        }
                    }
                }
            }
        }
    }

    property Item body: ListView {
        id: rows
        parent: table
        anchors.fill: parent
        anchors.topMargin: table.headerHeight
        clip: true
        model: table.model
        boundsBehavior: Flickable.StopAtBounds
        pressDelay: table.metrics.directTouch ? 100 : 0
        ScrollBar.vertical: ScrollBar {}
        delegate: Item {
            id: peopleRow
            property int rowIndex: index
            property var rowData: model
            property var styleData: ({row: rowIndex, selected: table.selection.contains(rowIndex),
                alternate: rowIndex % 2 === 1})
            width: rows.width
            height: Math.max(table.metrics.adaptiveMinimumControlHeight,
                background.item ? background.item.height : 60)
            Loader {
                id: background
                property var styleData: peopleRow.styleData
                width: parent.width
                sourceComponent: table.rowDelegate
            }
            MouseArea {
                anchors.fill: parent
                onClicked: {
                    table.selection.clear()
                    table.selection.select(peopleRow.rowIndex)
                }
            }
            Row {
                height: parent.height
                Repeater {
                    model: table.columns
                    delegate: Loader {
                        property var column: modelData
                        property var model: peopleRow.rowData
                        property var styleData: ({row: peopleRow.rowIndex, column: index,
                            role: column.role, value: model ? model[column.role] : undefined,
                            selected: peopleRow.styleData.selected, alternate: peopleRow.styleData.alternate})
                        width: column.visible ? Math.max(0, column.width) : 0
                        height: peopleRow.height
                        visible: column.visible
                        active: visible
                        sourceComponent: table.itemDelegate
                    }
                }
            }
        }
    }
}
