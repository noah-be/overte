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
    function test_narrowTouchLayout_data() { return [{tag: "phone", width: 320}, {tag: "tablet", width: 700}]; }
    function test_narrowTouchLayout(data) {
        page.width = data.width;
        page.height = 640;
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
}
