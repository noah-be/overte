import QtQuick 2.12
import QtTest 1.2

TestCase {
    name: "AndroidTestSupport"

    QtObject {
        id: state
        property bool visible: false
        property int backCount: 0
        function show() { visible = true }
        function hide() { visible = false }
        function handleBack() {
            backCount += 1
            if (visible) {
                visible = false
                return true
            }
            return false
        }
    }

    function init() {
        state.visible = false
        state.backCount = 0
    }

    function test_backClosesVisibleSurface() {
        state.show()
        compare(state.handleBack(), true)
        compare(state.visible, false)
        compare(state.backCount, 1)
    }

    function test_backIsNotConsumedWhenHidden() {
        compare(state.handleBack(), false)
        compare(state.backCount, 1)
    }
}
