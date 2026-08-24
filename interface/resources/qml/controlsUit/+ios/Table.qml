import QtQuick 2.15
import QtQuick.Controls 2.15

import "../../stylesUit"
import ".." as HifiControls

// Screen-space Qt 6 compatibility surface for legacy tablet tables. It keeps
// the model, sorting and selection API used by People while presenting rows as
// a direct-touch ListView. Desktop keeps the full Qt Quick Controls 1 table.
ListView {
    id: tableView

    property int colorScheme: hifi.colorSchemes.light
    readonly property bool isLightColorScheme: colorScheme === hifi.colorSchemes.light
    property bool expandSelectedRow: false
    property bool centerHeaderText: false
    property bool sortIndicatorVisible: false
    property bool headerVisible: false
    property int sortIndicatorColumn: 0
    property int sortIndicatorOrder: Qt.AscendingOrder
    property Component rowDelegate: null
    property Component itemDelegate: null
    property var titlePaintedPos: []
    readonly property var flickableItem: tableView
    readonly property var selection: selectionState
    readonly property int rowCount: count

    signal titlePaintedPosSignal(int column)

    clip: true
    boundsBehavior: Flickable.DragOverBounds
    flickDeceleration: 4000
    maximumFlickVelocity: 8000
    spacing: 1

    HifiConstants { id: hifi }

    Component.onCompleted: console.log(
        "OVERTE_IOS_TOUCH_UI_GATE stage=ios-table-ready rows=" + count
        + " columns=" + compatibilityColumns().length)
    onCountChanged: console.log(
        "OVERTE_IOS_TOUCH_UI_GATE stage=ios-table-row-count rows=" + count)

    QtObject {
        id: selectionState
        property var selectedIndexes: []
        readonly property bool hasSelection: selectedIndexes.length > 0
        readonly property int currentIndex: hasSelection
            ? selectedIndexes[selectedIndexes.length - 1] : -1
        signal selectionChanged()

        function contains(index) {
            return selectedIndexes.indexOf(index) !== -1
        }

        function clear() {
            if (selectedIndexes.length === 0) {
                return
            }
            selectedIndexes = []
            selectionChanged()
        }

        function select(indexOrIndexes) {
            var candidates = Array.isArray(indexOrIndexes)
                ? indexOrIndexes : [indexOrIndexes]
            var next = selectedIndexes.slice(0)
            for (var i = 0; i < candidates.length; ++i) {
                var candidate = Number(candidates[i])
                if (isFinite(candidate) && candidate >= 0
                        && next.indexOf(candidate) === -1) {
                    next.push(candidate)
                }
            }
            selectedIndexes = next
            selectionChanged()
        }

        function deselect(index) {
            var next = selectedIndexes.filter(function (candidate) {
                return candidate !== index
            })
            if (next.length !== selectedIndexes.length) {
                selectedIndexes = next
                selectionChanged()
            }
        }

        function forEach(callback) {
            selectedIndexes.forEach(callback)
        }
    }

    function compatibilityColumns() {
        var columns = []
        for (var i = 0; i < data.length; ++i) {
            var candidate = data[i]
            if (candidate && candidate.role !== undefined
                    && candidate.title !== undefined) {
                columns.push(candidate)
            }
        }
        return columns
    }

    function getColumn(index) {
        var columns = compatibilityColumns()
        return index >= 0 && index < columns.length ? columns[index] : null
    }

    function positionViewAtRow(row, mode) {
        positionViewAtIndex(row, mode)
    }

    function roleText(row, roleName) {
        if (!row || row[roleName] === undefined || row[roleName] === null) {
            return ""
        }
        return String(row[roleName])
    }

    function primaryText(row) {
        return roleText(row, "displayName") || roleText(row, "userName")
            || roleText(row, "name") || roleText(row, "placeName")
    }

    function secondaryText(row) {
        var username = roleText(row, "userName")
        var place = roleText(row, "placeName")
        var primary = primaryText(row)
        if (username && username !== primary && place) {
            return username + " · " + place
        }
        return username !== primary ? username : place
    }

    header: headerVisible ? headerComponent : null
    Component {
        id: headerComponent
        Rectangle {
            width: tableView.width
            height: Math.max(48, Math.ceil(48 * touchMetrics.textScale))
            color: tableView.isLightColorScheme ? "#d8d8d8" : "#383838"
            Text {
                anchors.fill: parent
                anchors.leftMargin: 18
                verticalAlignment: Text.AlignVCenter
                color: tableView.isLightColorScheme ? "#303030" : "#f0f0f0"
                font.pixelSize: Math.round(18 * touchMetrics.textScale)
                text: qsTr("%1 PEOPLE").arg(tableView.count)
            }
        }
    }

    HifiControls.TouchUiMetrics { id: touchMetrics }

    delegate: Rectangle {
        id: row
        width: tableView.width
        height: Math.max(64, touchMetrics.adaptiveMinimumControlHeight)
        color: selectionState.contains(index)
            ? "#34a2c7" : index % 2 === 0 ? "#f4f4f4" : "#e8e8e8"

        Column {
            anchors {
                left: parent.left
                right: parent.right
                leftMargin: 18
                rightMargin: 18
                verticalCenter: parent.verticalCenter
            }
            spacing: 2

            Text {
                width: parent.width
                elide: Text.ElideRight
                color: selectionState.contains(index) ? "white" : "#303030"
                font.pixelSize: Math.round(18 * touchMetrics.textScale)
                text: tableView.primaryText(model)
            }
            Text {
                width: parent.width
                visible: text !== ""
                elide: Text.ElideRight
                color: selectionState.contains(index) ? "#e8f8ff" : "#666666"
                font.pixelSize: Math.round(14 * touchMetrics.textScale)
                text: tableView.secondaryText(model)
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: {
                selectionState.clear()
                selectionState.select(index)
                console.log(
                    "OVERTE_IOS_TOUCH_UI_GATE stage=ios-table-row-selected index=" + index)
            }
        }
    }

    ScrollBar.vertical: ScrollBar {
        policy: ScrollBar.AsNeeded
    }
}
