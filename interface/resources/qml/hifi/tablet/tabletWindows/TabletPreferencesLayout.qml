import QtQuick 2.7

// Keeps the shared preferences dialog unchanged unless a platform selector
// explicitly adapts it for a scaled screen-space host.
QtObject {
    property bool compactFooter: false
    property int buttonWidth: 120
    property int buttonHeight: 28
    property int buttonFontSize: 9
    property int buttonSpacing: 11
}
