import QtQuick 2.12

Item {
    property string text: ""
    property var androidClickAction
    property bool highlighted: false
    property int fontSize: font.pixelSize
    property font font
    signal clicked()

    onClicked: if (androidClickAction) androidClickAction()
}
