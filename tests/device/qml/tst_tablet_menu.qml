import QtQuick 2.12
import QtTest 1.2
import "../../../interface/resources/qml/hifi/tablet" as TabletUi
import "../../../interface/resources/qml/controls" as Controls

TestCase {
    id: tabletRoot
    name: "SharedTabletMenu"
    when: windowShown
    visible: true
    width: 768
    height: 900
    property bool screenSpaceMode: true
    function playButtonClickSound() {}
    Component { id: pageFactory; TabletUi.TabletMenu {} }
    Component { id: menuFactory; Controls.WrappedMenu {} }
    Component { id: itemFactory; Controls.WrappedMenuItem {} }
    Component { id: separatorFactory; Controls.WrappedMenuSeparator {} }
    SignalSpy { id: spy }

    function test_menuNavigationAndDispatch() {
        var page = createTemporaryObject(pageFactory, tabletRoot)
        var root = createTemporaryObject(menuFactory, tabletRoot)
        var settings = createTemporaryObject(menuFactory, root, {title: "Settings"})
        root.addMenuWrap(settings)
        var toggle = createTemporaryObject(itemFactory, tabletRoot,
            {text: "Test toggle", checkable: true})
        // The real bridge connects triggered to QAction::trigger, which updates
        // checked state back into the QML item. Simulate only that boundary.
        toggle.triggered.connect(function() { toggle.checked = !toggle.checked })
        var forbidden = createTemporaryObject(itemFactory, tabletRoot, {text: "General..."})
        settings.addItemWrap(toggle)
        settings.addItemWrap(forbidden)
        settings.addItemWrap(createTemporaryObject(separatorFactory, tabletRoot))
        compare(root.items.length, 1)
        compare(root.items[0], settings)
        compare(settings.items.length, 3)
        verify(!root.visible) // The native popup never needs to be opened.
        page.setRootMenu(root, "")
        var stack = findChild(page, "stack")
        compare(stack.depth, 1)
        tryVerify(function() { return stack.currentItem.currentItem !== null })
        verify(stack.currentItem.currentItem.visible)
        var firstRow = stack.currentItem.currentItem
        verify(firstRow.mapToItem(page, 0, 0).y >= 90)
        waitForRendering(firstRow)
        mouseClick(firstRow, firstRow.width / 2, firstRow.height / 2)
        tryCompare(stack, "depth", 2)
        tryVerify(function() { return stack.currentItem.currentItem !== null })
        spy.target = toggle
        spy.signalName = "triggered"
        spy.clear()
        stack.currentItem.selectCurrentItem()
        tryCompare(spy, "count", 1)
        verify(toggle.checked)
        toggle.enabled = false
        stack.currentItem.selectCurrentItem()
        wait(5)
        compare(spy.count, 1)
        toggle.enabled = true
        stack.currentItem.selectCurrentItem()
        toggle.enabled = false // Revalidate after the deferred dispatch.
        wait(5)
        compare(spy.count, 1)
        stack.currentItem.nextItem()
        spy.target = forbidden
        spy.clear()
        stack.currentItem.selectCurrentItem()
        wait(5)
        compare(spy.count, 0)
        verify(page.handleTabletBack())
        compare(stack.depth, 1)
        verify(!page.handleTabletBack())
        spy.target = null
    }

    function test_liveVisibilityAndInsertion() {
        var menu = createTemporaryObject(menuFactory, tabletRoot)
        var first = createTemporaryObject(itemFactory, tabletRoot, {text: "First"})
        var second = createTemporaryObject(itemFactory, tabletRoot, {text: "Second"})
        menu.addItemWrap(second)
        verify(menu.insertItemWrap(second, first))
        compare(menu.items[0], first)
        compare(menu.items[1], second)
        first.tabletVisible = false
        spy.target = first
        spy.signalName = "triggered"
        spy.clear()
        first.trigger()
        compare(spy.count, 0)
        first.tabletVisible = true
        first.trigger()
        compare(spy.count, 1)
        spy.target = null
    }
}
