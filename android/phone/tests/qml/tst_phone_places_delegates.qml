// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.12
import QtTest 1.2
import QtQuick.Window 2.2
import "production" as Production

TestCase {
    id: testCase
    name: "PhonePlacesDelegates"
    width: 720
    height: 850
    visible: true
    when: windowShown
    property var page: null
    Component { id: factory; Production.PicoPlaces { height: 750 } }
    SignalSpy { id: messages; target: page; signalName: "sendToScript" }

    function namedItems(item, name) {
        var result = item.objectName === name ? [item] : [];
        for (var i = 0; i < item.children.length; ++i)
            result = result.concat(namedItems(item.children[i], name));
        return result;
    }
    function init() {
        page = createTemporaryObject(factory, testCase);
        verify(page !== null);
        wait(50);
    }
    function cleanup() { page = null; }
    function test_selectedDelegateRemainsReadableAndActionable() {
        checkSelectedDelegate({width: 320, scale: 1});
    }
    function test_narrowLargeTextRemainsActionable() {
        checkSelectedDelegate({width: 320, scale: 1.5});
    }
    function test_wideLargeTextRemainsActionable() {
        checkSelectedDelegate({width: 700, scale: 1.5});
    }
    function checkSelectedDelegate(data) {
        page.width = data.width;
        var metrics = findChild(page, "placesTouchMetrics");
        verify(metrics !== null);
        metrics.profile.directTouch = true;
        metrics.profile.fontScale = data.scale;
        var rows = [];
        for (var i = 0; i < 30; ++i)
            rows.push({name: "Choice " + i, address: "hifi://choice-" + i, maturity: "everyone"});
        page.fromScript({channel: "com.overte.places", action: "PLACE_DATA",
                         data: rows, metaverseServers: []});
        wait(100);
        var buttons = namedItems(page, "visitPlace");
        verify(buttons.length > 0);
        var list = buttons[0].parent;
        while (list && typeof list.positionViewAtIndex !== "function") list = list.parent;
        verify(list !== null, "Actual delegate must belong to a scrollable ListView");
        list.positionViewAtIndex(17, ListView.Center);
        var selected = null;
        tryVerify(function() {
            var current = namedItems(page, "visitPlace");
            for (var n = 0; n < current.length; ++n)
                if (current[n].text.indexOf("Choice 17\n") === 0) selected = current[n];
            return selected !== null;
        });
        wait(100);
        verify(list.contentY > 0, "Selection must exercise a scrolled delegate");
        verify(selected.height >= Math.max(48, metrics.adaptiveMinimumControlHeight));
        verify(selected.height + 1 >= selected.contentItem.implicitHeight + selected.topPadding + selected.bottomPadding,
               "The selected label must fit at the actual font scale");
        verify(selected.font.pixelSize >= Math.round(20 * data.scale));
        var position = selected.mapToItem(page, 0, 0);
        verify(position.x >= 0 && position.x + selected.width <= page.width + 1,
               "Selected control x=" + position.x + " width=" + selected.width + " page=" + page.width);
        verify(position.y >= 0 && position.y + selected.height <= page.height + 1);
        var ancestor = selected;
        while (ancestor) {
            verify(ancestor.visible, "The actual pointer target and its ancestors must be visible");
            ancestor = ancestor.parent;
        }
        messages.clear();
        mousePress(selected, selected.width / 2, selected.height / 2);
        wait(150); // Exercise the actual direct-touch Flickable press delay.
        mouseRelease(selected, selected.width / 2, selected.height / 2);
        tryCompare(messages, "count", 1, 1500,
                   "Actual window=" + page.Window.window.width + "x" + page.Window.window.height
                   + " button at=" + position.x + "," + position.y
                   + " size=" + selected.width + "x" + selected.height);
        compare(messages.signalArguments[0][0].action, "TELEPORT");
        compare(messages.signalArguments[0][0].name, "Choice 17");
        compare(messages.signalArguments[0][0].address, "hifi://choice-17");
    }
}
