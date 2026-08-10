import QtQuick 2.7

QtObject {
    // WindowRoot already scales this complete surface by 2.5. Normal logical
    // dimensions avoid applying the generic Android 3x constants underneath
    // that host scale and overflowing the lower-right footer.
    property bool compactFooter: true
    property int buttonWidth: 120
    property int buttonHeight: 28
    property int buttonFontSize: 9
    property int buttonSpacing: 11
}
