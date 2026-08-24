import QtQuick 2.15

// Qt Quick Controls 2 removed TableViewColumn. The iOS Table adapter consumes
// this metadata to retain the existing model/sorting contract without loading
// Qt Quick Controls 1.
QtObject {
    property string role: ""
    property string title: ""
    property real width: 0
    property bool movable: false
    property bool resizable: false
    property bool visible: true
}
