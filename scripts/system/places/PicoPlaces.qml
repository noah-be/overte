import QtQuick 2.7
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import controlsUit 1.0 as HifiControls

Rectangle {
    id: root
    readonly property string semanticScreenId: "places.home"
    HifiControls.TouchUiMetrics { id: touchMetrics; availableWidth: root.width; availableHeight: root.height }
    color: "#303030"
    signal sendToScript(var message)
    // OffscreenQmlSurface raises the established headset keyboard on focus.
    // Native touch hosts continue to use their system IME.
    property bool keyboardEnabled: false
    property bool keyboardRaised: false
    property bool punctuationMode: false
    property var keyboardItem: null
    onKeyboardRaisedChanged: {
        if (typeof KeyboardScriptingInterface !== "undefined" && KeyboardScriptingInterface.use3DKeyboard) {
            KeyboardScriptingInterface.raised = keyboardEnabled && keyboardRaised;
        }
    }
    onKeyboardEnabledChanged: {
        if (keyboardEnabled && !keyboardItem && typeof KeyboardScriptingInterface !== "undefined"
                && !KeyboardScriptingInterface.use3DKeyboard) {
            keyboardItem = Qt.createQmlObject('import QtQuick 2.7; import controlsUit 1.0; Keyboard {'
                + ' anchors.bottom: parent.bottom; raised: parent.keyboardEnabled && parent.keyboardRaised;'
                + ' numeric: parent.punctuationMode }', root, "NativePlacesKeyboard");
        }
    }
    Component.onDestruction: {
        if (keyboardRaised && typeof KeyboardScriptingInterface !== "undefined"
                && KeyboardScriptingInterface.use3DKeyboard) KeyboardScriptingInterface.raised = false;
    }
    property string channel: "com.overte.places"
    property bool loading: true
    property string currentAddress: ""
    property string directoryWarning: ""
    property var records: []
    property var bookmarkAddresses: ({})
    property var maturityFilter: ["adult", "mature", "teen", "everyone", "unrated"]
    property var pendingCommands: []
    readonly property int placeCount: placesModel.count
    readonly property int bookmarkCount: bookmarksModel.count
    readonly property int serverCount: serversModel.count
    readonly property int controlHeight: Math.max(48, touchMetrics.adaptiveMinimumControlHeight)

    ListModel { id: placesModel }
    ListModel { id: bookmarksModel }
    ListModel { id: serversModel }

    // The shared script rate-limits commands to 200 ms. Preserve every user
    // action, including the refresh following a server change, in order.
    Timer {
        id: commandInterval
        interval: 230
        onTriggered: {
            if (root.pendingCommands.length) {
                var commands = root.pendingCommands.slice();
                root.sendToScript(commands.shift());
                root.pendingCommands = commands;
                restart();
            }
        }
    }
    function dispatch(action, fields) {
        var message = fields || {};
        message.channel = channel;
        message.action = action;
        if (commandInterval.running) {
            pendingCommands = pendingCommands.concat([message]);
        } else {
            sendToScript(message);
            commandInterval.start();
        }
    }
    function requestContent() {
        loading = true;
        dispatch("READY_FOR_CONTENT");
    }
    function rebuildPlaces() {
        placesModel.clear();
        var query = search.text.trim().toLowerCase();
        for (var i = 0; i < records.length; ++i) {
            var place = records[i];
            if (!place || typeof place.address !== "string") continue;
            var name = place.name || place.address || qsTr("Unnamed place");
            var description = place.description || "";
            // Packaged utility entries use category Z and remain accessible.
            if (place.category !== "Z" && place.maturity && maturityFilter.indexOf(place.maturity) === -1) continue;
            if (query && (name + " " + description + " " + place.address).toLowerCase().indexOf(query) === -1) continue;
            placesModel.append({placeName: name, placeAddress: place.address,
                placeDescription: description, attendance: Number(place.current_attendance || 0),
                capacity: Number(place.capacity || 0), placeId: place.placeID || place.id || ""});
        }
    }
    function toggleMaturity(rating, included) {
        var filter = maturityFilter.filter(function(value) { return value !== rating; });
        if (included) filter.push(rating);
        maturityFilter = filter;
        rebuildPlaces();
        dispatch("SET_MATURITY_FILTER", {filter: filter});
    }
    function changeServer(index, action, value) {
        dispatch(action, {metaverseIndex: index, value: value});
        requestContent();
    }
    function fromScript(message) {
        if (!message || message.channel !== channel) return;
        if (message.action === "PLACE_DATA") {
            records = Array.isArray(message.data) ? message.data : [];
            directoryWarning = message.warning || "";
            serversModel.clear();
            var servers = message.metaverseServers || [];
            for (var i = 0; i < servers.length; ++i) {
                var server = servers[i];
                if (!server || typeof server.url !== "string") continue;
                serversModel.append({serverUrl: server.url, serverIndex: i,
                    serverRegion: server.region || "", fetched: server.fetch === true,
                    pinned: server.pinned === true, failed: server.error === true});
            }
            rebuildPlaces();
            loading = false;
        } else if (message.action === "MATURITY_FILTER" && Array.isArray(message.filter)) {
            maturityFilter = message.filter.slice();
            rebuildPlaces();
        } else if (message.action === "CURRENT_LOCATION") {
            currentAddress = typeof message.data === "string" ? message.data : "";
        } else if (message.action === "BOOKMARKS_DATA") {
            bookmarkAddresses = message.data || {};
            bookmarksModel.clear();
            var names = Object.keys(bookmarkAddresses).sort();
            for (var b = 0; b < names.length; ++b) {
                if (typeof bookmarkAddresses[names[b]] === "string") {
                    bookmarksModel.append({bookmarkName: names[b], bookmarkAddress: bookmarkAddresses[names[b]]});
                }
            }
        }
    }
    function editBookmark(name, address) {
        bookmarkDialog.originalName = name;
        bookmarkDialog.address = address;
        bookmarkName.text = name;
        bookmarkDialog.open();
    }
    function validBookmarkName() {
        var name = bookmarkName.text.trim();
        return name.length > 0 && (name === bookmarkDialog.originalName ||
            !Object.prototype.hasOwnProperty.call(bookmarkAddresses, name));
    }
    Component.onCompleted: Qt.callLater(requestContent)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        anchors.bottomMargin: 12 + (root.keyboardItem ? root.keyboardItem.height : 0)
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            Text { text: qsTr("OVERTE PLACES"); color: "white"; font.bold: true
                font.pixelSize: Math.round(22 * touchMetrics.textScale); Layout.fillWidth: true }
            Button { objectName: "refreshPlaces"; text: qsTr("Refresh"); implicitHeight: root.controlHeight
                enabled: !root.loading; onClicked: root.requestContent() }
        }
        RowLayout {
            Layout.fillWidth: true
            Button { objectName: "goBack"; text: qsTr("Back"); implicitHeight: root.controlHeight
                Layout.fillWidth: true; onClicked: root.dispatch("GO_BACK") }
            Button { objectName: "goForward"; text: qsTr("Forward"); implicitHeight: root.controlHeight
                Layout.fillWidth: true; onClicked: root.dispatch("GO_FORWARD") }
            Button { objectName: "goHome"; text: qsTr("Home"); implicitHeight: root.controlHeight
                Layout.fillWidth: true; onClicked: root.dispatch("GO_HOME") }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: root.currentAddress; color: "#dddddd"; elide: Text.ElideMiddle
                Layout.fillWidth: true; Accessible.name: qsTr("Current location") }
            Button { objectName: "locationActions"; text: qsTr("Location"); implicitHeight: root.controlHeight
                enabled: root.currentAddress !== ""; onClicked: locationMenu.open() }
            Menu {
                id: locationMenu
                MenuItem { objectName: "copyCurrentLocation"; text: qsTr("Copy address")
                    onTriggered: root.dispatch("COPY_URL", {address: root.currentAddress}) }
                MenuItem { objectName: "setCurrentHome"; text: qsTr("Set as Home")
                    onTriggered: root.dispatch("SET_HOME") }
            }
        }
        Text { Layout.fillWidth: true; visible: root.directoryWarning !== ""; text: root.directoryWarning
            color: "#ffdc8a"; wrapMode: Text.WordWrap }
        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { objectName: "placesTab"; text: qsTr("Places"); implicitHeight: root.controlHeight }
            TabButton { objectName: "bookmarksTab"; text: qsTr("Bookmarks"); implicitHeight: root.controlHeight }
            TabButton { objectName: "serversTab"; text: qsTr("Servers"); implicitHeight: root.controlHeight }
        }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: search; objectName: "placesSearch"; placeholderText: qsTr("Search places")
                        Layout.fillWidth: true; implicitHeight: root.controlHeight; onTextChanged: root.rebuildPlaces() }
                    Button { objectName: "maturityFilters"; text: qsTr("Ratings"); implicitHeight: root.controlHeight
                        onClicked: ratingPopup.open() }
                }
                Text { Layout.fillWidth: true; visible: root.loading; text: qsTr("Loading current domain directory...")
                    color: "#b8e6ff"; wrapMode: Text.WordWrap }
                Text { Layout.fillWidth: true; visible: !root.loading && placesModel.count === 0
                    text: qsTr("No compatible places match these filters."); color: "#dddddd"; wrapMode: Text.WordWrap }
                ListView {
                    id: placesList
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    boundsBehavior: Flickable.StopAtBounds; pressDelay: touchMetrics.directTouch ? 100 : 0
                    spacing: 8; model: placesModel
                    ScrollBar.vertical: ScrollBar {}
                    delegate: ColumnLayout {
                        width: placesList.width
                        spacing: 0
                        Button {
                            objectName: "visitPlace"; Layout.fillWidth: true; implicitHeight: Math.max(64, root.controlHeight)
                            text: placeName + "\n" + (capacity > 0 ? attendance + "/" + capacity : attendance + qsTr(" online"))
                            enabled: placeAddress !== ""
                            onClicked: root.dispatch("TELEPORT", {name: placeName, address: placeAddress})
                        }
                        Text { Layout.fillWidth: true; text: placeDescription || placeAddress; color: "#dddddd"
                            elide: Text.ElideRight; font.pixelSize: Math.round(15 * touchMetrics.textScale) }
                        RowLayout {
                            Button { objectName: "copyPlace"; text: qsTr("Copy address"); implicitHeight: root.controlHeight
                                enabled: placeAddress !== ""; onClicked: root.dispatch("COPY_URL", {address: placeAddress}) }
                            Button { objectName: "createPlacePortal"; text: qsTr("Create portal"); implicitHeight: root.controlHeight
                                enabled: placeAddress !== ""; onClicked: root.dispatch("REQUEST_PORTAL",
                                    {name: placeName, address: placeAddress, placeID: placeId}) }
                        }
                    }
                }
            }
            ColumnLayout {
                Button { objectName: "addBookmark"; text: qsTr("Bookmark current location"); implicitHeight: root.controlHeight
                    Layout.fillWidth: true; enabled: root.currentAddress !== ""; onClicked: root.editBookmark("", root.currentAddress) }
                Text { visible: bookmarksModel.count === 0; text: qsTr("No saved bookmarks."); color: "#dddddd" }
                ListView {
                    id: bookmarksList
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 12; model: bookmarksModel
                    boundsBehavior: Flickable.StopAtBounds; pressDelay: touchMetrics.directTouch ? 100 : 0
                    ScrollBar.vertical: ScrollBar {}
                    delegate: ColumnLayout {
                        width: bookmarksList.width
                        Button { objectName: "visitBookmark"; text: bookmarkName; Layout.fillWidth: true
                            implicitHeight: root.controlHeight; onClicked: root.dispatch("TELEPORT",
                                {name: bookmarkName, address: bookmarkAddress}) }
                        Text { text: bookmarkAddress; color: "#dddddd"; Layout.fillWidth: true; elide: Text.ElideMiddle }
                        RowLayout {
                            Button { objectName: "renameBookmark"; text: qsTr("Rename"); implicitHeight: root.controlHeight
                                onClicked: root.editBookmark(bookmarkName, bookmarkAddress) }
                            Button { objectName: "deleteBookmark"; text: qsTr("Delete"); implicitHeight: root.controlHeight
                                onClicked: root.dispatch("DELETE_BOOKMARK", {name: bookmarkName}) }
                        }
                    }
                }
            }
            ColumnLayout {
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: newServer; objectName: "newServerUrl"; placeholderText: qsTr("https://directory.example")
                        implicitHeight: root.controlHeight; Layout.fillWidth: true }
                    Button { objectName: "addServer"; text: qsTr("Add"); implicitHeight: root.controlHeight
                        enabled: !root.loading && /^https?:\/\/[^\s/?#]+(?:\/[^\s]*)?$/.test(newServer.text.trim())
                        onClicked: { root.dispatch("ADD_MS", {metaverseUrl: newServer.text.trim()}); newServer.clear(); root.requestContent(); } }
                }
                ListView {
                    id: serversList
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 12; model: serversModel
                    boundsBehavior: Flickable.StopAtBounds; pressDelay: touchMetrics.directTouch ? 100 : 0
                    ScrollBar.vertical: ScrollBar {}
                    delegate: ColumnLayout {
                        width: serversList.width
                        Text { text: serverUrl; color: "white"; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
                        Text { text: failed ? qsTr("Directory unavailable. Refresh to retry.") : serverRegion
                            color: failed ? "#ffdc8a" : "#dddddd"; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        RowLayout {
                            CheckBox { objectName: "fetchServer"; text: qsTr("Fetch"); checked: fetched; implicitHeight: root.controlHeight
                                enabled: !root.loading; onClicked: root.changeServer(serverIndex, "FETCH_META", checked) }
                            CheckBox { objectName: "pinServer"; text: qsTr("Pin"); checked: pinned; implicitHeight: root.controlHeight
                                enabled: !root.loading; onClicked: root.changeServer(serverIndex, "PIN_META", checked) }
                        }
                    }
                }
            }
        }
    }
    Popup {
        id: ratingPopup
        x: Math.max(0, root.width - width - 12); y: 140
        width: Math.min(root.width - 24, 260)
        contentItem: ColumnLayout {
            Repeater {
                model: ["everyone", "teen", "mature", "adult", "unrated"]
                CheckBox { objectName: "rating_" + modelData; text: modelData; implicitHeight: root.controlHeight
                    checked: root.maturityFilter.indexOf(modelData) !== -1
                    onClicked: root.toggleMaturity(modelData, checked) }
            }
        }
    }
    Dialog {
        id: bookmarkDialog
        property string originalName: ""
        property string address: ""
        x: (root.width - width) / 2; y: Math.max(0, (root.height - (root.keyboardItem ? root.keyboardItem.height : 0) - height) / 2)
        width: Math.min(root.width - 24, 500)
        modal: true
        title: originalName ? qsTr("Rename bookmark") : qsTr("Add bookmark")
        contentItem: ColumnLayout {
            TextField { id: bookmarkName; objectName: "bookmarkName"; placeholderText: qsTr("Bookmark name")
                Layout.fillWidth: true; implicitHeight: root.controlHeight; selectByMouse: true }
            Text { text: bookmarkDialog.address; color: "#555555"; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            Text { text: qsTr("Choose a new, nonempty name."); visible: !root.validBookmarkName()
                color: "#9d241a"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        footer: DialogButtonBox {
            Button { objectName: "saveBookmark"; text: qsTr("Save"); implicitHeight: root.controlHeight
                enabled: root.validBookmarkName()
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole }
            Button { text: qsTr("Cancel"); implicitHeight: root.controlHeight
                DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
            onAccepted: {
                var name = bookmarkName.text.trim();
                if (bookmarkDialog.originalName && name !== bookmarkDialog.originalName) {
                    root.dispatch("RENAME_BOOKMARK", {originalName: bookmarkDialog.originalName, name: name, url: bookmarkDialog.address});
                } else if (!bookmarkDialog.originalName) {
                    root.dispatch("ADD_BOOKMARK", {name: name});
                }
                bookmarkDialog.close();
            }
            onRejected: bookmarkDialog.close()
        }
    }
}
