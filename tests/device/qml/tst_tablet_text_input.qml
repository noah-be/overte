import QtQuick 2.12
import QtTest 1.2
import controlsUit 1.0 as HifiControls

TestCase {
    name: "SharedTabletTextInput"
    when: windowShown
    visible: true
    width: 400
    height: 200
    Component { id: fieldFactory; HifiControls.TextField {} }
    SignalSpy { id: spy }

    function test_editClearAndAccept() {
        var field = createTemporaryObject(fieldFactory, this,
            {width: 320, hasClearButton: true, isSearchField: true,
             placeholderText: "Search", styleRenderType: Text.QtRendering})
        compare(field.renderType, Text.QtRendering)
        compare(field.placeholderText, "Search")
        field.forceActiveFocus()
        keyClick(Qt.Key_A)
        compare(field.text, "a")
        var clearButton = findChild(field, "textfield.clear")
        verify(clearButton.visible)
        waitForRendering(field)
        mouseClick(clearButton, clearButton.width / 2, clearButton.height / 2)
        compare(field.text, "")
        verify(!clearButton.visible)
        spy.target = field
        spy.signalName = "accepted"
        spy.clear()
        field.forceActiveFocus()
        keyClick(Qt.Key_Return)
        compare(spy.count, 1)
        spy.target = null
    }
}
