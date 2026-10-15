import QtQuick 2.7
import QtTest 1.2
import QtQuick.Window 2.2
import "production" as Production

TestCase {
    id: testCase
    name: "NativePlacesParity"
    when: windowShown
    visible: true
    width: 900
    height: 850
    property var page: null
    Component { id: factory; Production.PicoPlaces { width: 700; height: 750 } }
    SignalSpy { id: messages; target: page; signalName: "sendToScript" }
    function deliver(action, fields) {
        var message = fields || {};
        message.channel = "com.overte.places";
        message.action = action;
        page.fromScript(message);
    }
    function lookup(name) {
        return findChild(page, name) || findChild(testCase.Window.window.contentItem, name);
    }
    function control(name) {
        waitForRendering(page);
        tryVerify(function() { return lookup(name) !== null; }, 2500,
                  "Missing actual production control: " + name);
        return lookup(name);
    }
    function typeText(value) {
        for (var i = 0; i < value.length; ++i) {
            var c = value.charAt(i);
            var upper = c.toUpperCase();
            var modifier = c === upper && c !== c.toLowerCase() ? Qt.ShiftModifier : Qt.NoModifier;
            keyClick(upper.charCodeAt(0), modifier);
        }
    }
    function click(name) {
        var item = control(name);
        verify(item.visible && item.enabled, name + " is not actionable");
        mouseClick(item, item.width / 2, item.height / 2);
    }
    function lastMessage(action) {
        tryVerify(function() {
            return messages.signalArguments.some(function(args) { return args[0].action === action; });
        }, 2500);
        var found = messages.signalArguments.filter(function(args) { return args[0].action === action; });
        return found[found.length - 1][0];
    }
    function init() {
        testCase.Window.window.width = width;
        testCase.Window.window.height = height;
        page = createTemporaryObject(factory, testCase);
        verify(page !== null);
        lastMessage("READY_FOR_CONTENT");
        wait(250);
        messages.clear();
        deliver("CURRENT_LOCATION", {data: "hifi://current/1,2,3"});
        deliver("PLACE_DATA", {data: [], metaverseServers: []});
    }
    function cleanup() { page = null; }
    function test_persistedRatingsAndSearchKeepUtilityPlaces() {
        deliver("MATURITY_FILTER", {filter: ["everyone"]});
        deliver("PLACE_DATA", {data: [
            {name: "Public Hub", address: "hifi://public", maturity: "everyone"},
            {name: "Adult Hub", address: "hifi://adult", maturity: "adult"},
            {name: "tutorial", address: "file:///~/serverless/tutorial.json", maturity: "unrated", category: "Z"}
        ]});
        compare(page.placeCount, 2);
        var search = control("placesSearch");
        search.forceActiveFocus();
        typeText("Public");
        compare(page.placeCount, 1);
        click("visitPlace");
        compare(lastMessage("TELEPORT").address, "hifi://public");
        search.clear();
        click("maturityFilters");
        click("rating_adult");
        compare(page.placeCount, 3);
        verify(lastMessage("SET_MATURITY_FILTER").filter.indexOf("adult") !== -1);
    }
    function test_placeCopyAndPortalUseCurrentModelValues() {
        deliver("PLACE_DATA", {data: [{name: "Public Hub", address: "hifi://public", id: "place-1"}]});
        click("copyPlace");
        compare(lastMessage("COPY_URL").address, "hifi://public");
        click("createPlacePortal");
        var portal = lastMessage("REQUEST_PORTAL");
        compare(portal.name, "Public Hub");
        compare(portal.address, "hifi://public");
        compare(portal.placeID, "place-1");
    }
    function test_bookmarkCreateRenameDeleteAndVisit() {
        deliver("BOOKMARKS_DATA", {data: {Favorite: "hifi://favorite"}});
        click("bookmarksTab");
        compare(page.bookmarkCount, 1);
        click("visitBookmark");
        compare(lastMessage("TELEPORT").address, "hifi://favorite");
        click("renameBookmark");
        var field = control("bookmarkName");
        field.selectAll();
        field.forceActiveFocus();
        typeText("renamed");
        click("saveBookmark");
        var rename = lastMessage("RENAME_BOOKMARK");
        compare(rename.originalName, "Favorite");
        compare(rename.name, "renamed");
        compare(rename.url, "hifi://favorite");
        deliver("BOOKMARKS_DATA", {data: {renamed: "hifi://favorite"}});
        click("deleteBookmark");
        compare(lastMessage("DELETE_BOOKMARK").name, "renamed");
        deliver("BOOKMARKS_DATA", {data: {}});
        click("addBookmark");
        field = control("bookmarkName");
        verify(!control("saveBookmark").enabled);
        field.forceActiveFocus();
        typeText("current");
        click("saveBookmark");
        compare(lastMessage("ADD_BOOKMARK").name, "current");
    }
    function test_namePayloadPreservesCaseAndUnicode() {
        click("bookmarksTab");
        click("addBookmark");
        // Qt Quick's synthetic key driver supplies lowercase ASCII text even
        // with Shift on this host. Test the editor payload separately from the
        // actual lowercase key-input cases; this is not a physical IME claim.
        control("bookmarkName").text = "Ä New Place";
        click("saveBookmark");
        compare(lastMessage("ADD_BOOKMARK").name, "Ä New Place");
    }
    function test_duplicateAndUnchangedBookmarkNames() {
        deliver("BOOKMARKS_DATA", {data: {One: "hifi://one", Two: "hifi://two"}});
        click("bookmarksTab");
        click("renameBookmark");
        var field = control("bookmarkName");
        var original = field.text;
        click("saveBookmark");
        wait(300);
        compare(messages.count, 0, "Unchanged rename must not remove the bookmark in the script");
        click("renameBookmark");
        field.text = original === "One" ? "Two" : "One";
        verify(!control("saveBookmark").enabled, "Existing bookmark must not be overwritten");
    }
    function test_serverActionsPreserveIndexAndOrderedRefresh() {
        deliver("PLACE_DATA", {data: [], warning: "Different protocol", metaverseServers: [
            null, {url: "https://meta.example", region: "external", fetch: false, pinned: true, error: true}
        ]});
        compare(page.directoryWarning, "Different protocol");
        compare(page.serverCount, 1);
        click("serversTab");
        click("fetchServer");
        var fetch = lastMessage("FETCH_META");
        compare(fetch.metaverseIndex, 1);
        compare(fetch.value, true);
        lastMessage("READY_FOR_CONTENT");
        compare(messages.signalArguments[0][0].action, "FETCH_META");
        compare(messages.signalArguments[1][0].action, "READY_FOR_CONTENT");
    }
    function test_addDirectoryAndPin() {
        click("serversTab");
        var field = control("newServerUrl");
        field.text = "javascript:alert(1)";
        verify(!control("addServer").enabled);
        field.forceActiveFocus();
        field.selectAll();
        typeText("https://new.example");
        click("addServer");
        compare(lastMessage("ADD_MS").metaverseUrl, "https://new.example");
        lastMessage("READY_FOR_CONTENT");
        deliver("PLACE_DATA", {data: [], metaverseServers: [
            {url: "https://new.example", fetch: false, pinned: true}
        ]});
        click("pinServer");
        compare(lastMessage("PIN_META").value, false);
    }
    function test_navigationActionsQueuedWithoutLoss() {
        click("goBack");
        click("goForward");
        click("goHome");
        lastMessage("GO_HOME");
        compare(messages.signalArguments.map(function(args) { return args[0].action; }).join(","),
                "GO_BACK,GO_FORWARD,GO_HOME");
        click("locationActions");
        click("copyCurrentLocation");
        compare(lastMessage("COPY_URL").address, "hifi://current/1,2,3");
        click("locationActions");
        click("setCurrentHome");
        lastMessage("SET_HOME");
    }
    function test_narrowTouchLayout_data() {
        return [{tag: "phone", width: 320, fontScale: 1},
                {tag: "phone-large-text", width: 320, fontScale: 1.5},
                {tag: "tablet", width: 700, fontScale: 1}];
    }
    function test_narrowTouchLayout(data) {
        page.width = data.width;
        page.height = 640;
        var metrics = control("placesTouchMetrics");
        metrics.profile.directTouch = true;
        metrics.profile.fontScale = data.fontScale;
        wait(30);
        for (var i = 0; i < 3; ++i) {
            var tab = control(["placesTab", "bookmarksTab", "serversTab"][i]);
            mouseClick(tab, tab.width / 2, tab.height / 2);
            var button = control(["maturityFilters", "addBookmark", "addServer"][i]);
            var pos = button.mapToItem(page, 0, 0);
            verify(button.height >= 48);
            verify(pos.x >= 0 && pos.x + button.width <= page.width + 1,
                "Action extends outside the actual narrow surface");
        }
    }
    function namedItems(item, name) {
        var items = item.objectName === name ? [item] : [];
        for (var i = 0; i < item.children.length; ++i)
            items = items.concat(namedItems(item.children[i], name));
        return items;
    }
    function test_scrolledPlaceDelegate_data() {
        return [{tag: "narrow", width: 320, fontScale: 1},
                {tag: "narrow-large-text", width: 320, fontScale: 1.5},
                {tag: "wide-large-text", width: 700, fontScale: 1.5}];
    }
    function pressScrolledControl(item, list) {
        verify(page.visible && item.visible && item.enabled && testCase.Window.window.visible);
        verify(!list.moving);
        var position = item.mapToItem(list, 0, 0);
        verify(position.x >= 0 && position.x + item.width <= list.width + 1);
        verify(position.y >= 0 && position.y + item.height <= list.height + 1,
               "The real pointer target must be inside the scrolled viewport");
        mousePress(item, item.width / 2, item.height / 2);
        wait(list.pressDelay + 50);
        verify(item.pressed, "The actual control must receive the delayed pointer press");
        mouseRelease(item, item.width / 2, item.height / 2);
    }
    function test_scrolledPlaceDelegate(data) {
        page.width = data.width;
        var metrics = control("placesTouchMetrics");
        metrics.profile.directTouch = true;
        metrics.profile.fontScale = data.fontScale;
        var records = [];
        for (var i = 0; i < 30; ++i)
            records.push({name: "Choice " + i, address: "hifi://choice-" + i,
                          placeID: "place-" + i, maturity: "everyone"});
        deliver("PLACE_DATA", {data: records, metaverseServers: []});
        var list = control("visitPlace").parent;
        while (list && typeof list.positionViewAtIndex !== "function") list = list.parent;
        verify(list !== null, "The production delegate must belong to a scrollable ListView");
        compare(list.pressDelay, 100, "Exercise the actual direct-touch press delay");
        list.cancelFlick();
        list.positionViewAtIndex(17, ListView.Center);
        var selected = null;
        tryVerify(function() {
            var buttons = namedItems(page, "visitPlace");
            for (var b = 0; b < buttons.length; ++b)
                if (buttons[b].text.indexOf("Choice 17\n") === 0) selected = buttons[b];
            return selected !== null && !list.moving;
        });
        verify(waitForRendering(page));
        verify(list.contentY > 0, "Exercise a delegate beyond the initial viewport");
        var position = selected.mapToItem(page, 0, 0);
        var windowPosition = selected.mapToItem(testCase.Window.window.contentItem, 0, 0);
        var copy = findChild(selected.parent, "copyPlace");
        var portal = findChild(selected.parent, "createPlacePortal");
        verify(copy !== null && portal !== null);
        console.log("Scrolled Places geometry: page=" + page.width + " window="
                    + testCase.Window.window.width + "x" + testCase.Window.window.height
                    + " list=" + list.width + " delegate=" + selected.parent.width
                    + " minimum=" + selected.parent.implicitWidth + " visit=" + selected.width
                    + " actionsMinimum=" + copy.parent.implicitWidth
                    + " copyMinimum=" + copy.implicitWidth + " portalMinimum=" + portal.implicitWidth);
        verify(position.x >= 0 && position.x + selected.width <= page.width + 1,
               "Selected control x=" + position.x + " width=" + selected.width + " page=" + page.width);
        verify(position.y >= 0 && position.y + selected.height <= page.height + 1);
        verify(windowPosition.x >= 0 && windowPosition.x + selected.width <= testCase.Window.window.width);
        verify(windowPosition.y >= 0 && windowPosition.y + selected.height <= testCase.Window.window.height);
        verify(selected.height >= Math.max(48, metrics.adaptiveMinimumControlHeight));
        verify(selected.height + 1 >= selected.contentItem.implicitHeight + selected.topPadding + selected.bottomPadding);
        verify(selected.font.pixelSize >= Math.round(20 * data.fontScale));
        compare(copy.text, qsTr("Copy address"));
        compare(portal.text, qsTr("Create portal"));
        for (var a = 0; a < 2; ++a) {
            var action = [copy, portal][a];
            var actionPosition = action.mapToItem(page, 0, 0);
            verify(action.visible && action.enabled);
            verify(action.height >= Math.max(48, metrics.adaptiveMinimumControlHeight));
            verify(action.font.pixelSize >= Math.round(16 * data.fontScale));
            verify(action.width + 1 >= action.contentItem.implicitWidth + action.leftPadding + action.rightPadding,
                   "The complete action label must fit without shrinking its font");
            verify(actionPosition.x >= 0 && actionPosition.x + action.width <= page.width + 1);
            verify(actionPosition.y >= 0 && actionPosition.y + action.height <= page.height + 1);
        }
        messages.clear();
        pressScrolledControl(selected, list);
        var message = lastMessage("TELEPORT");
        compare(message.name, "Choice 17");
        compare(message.address, "hifi://choice-17");
        compare(messages.count, 1);
        messages.clear();
        pressScrolledControl(copy, list);
        compare(lastMessage("COPY_URL").address, "hifi://choice-17");
        compare(messages.count, 1);
        messages.clear();
        pressScrolledControl(portal, list);
        var portalMessage = lastMessage("REQUEST_PORTAL");
        compare(portalMessage.name, "Choice 17");
        compare(portalMessage.address, "hifi://choice-17");
        compare(portalMessage.placeID, "place-17");
        compare(messages.count, 1);
    }
}
