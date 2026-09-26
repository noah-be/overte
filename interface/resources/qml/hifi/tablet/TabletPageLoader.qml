import QtQuick 2.7

// Kept separate from the window so real load/error/navigation races can be
// tested with a controlled surface without constructing native client services.
Item {
    id: loader
    objectName: "loader"
    property var surface: QmlSurface
    property string source: ""
    property var item: null
    property bool loadFailed: false
    property int qmlLoadGeneration: 0
    property bool sharedTouchNavigation: false
    property var rootMenu
    property string subMenu: ""
    signal loaded()
    signal screenChanged(var type, var url)
    signal sendToScript(var message)
    signal homeRequested()

    TabletPageStatus {
        anchors.fill: parent
        visible: loader.source !== "" && loader.item === null
        failed: loader.loadFailed
        onHomeRequested: loader.homeRequested()
    }
    Connections {
        target: loader.surface
        function onQmlLoadFailed(failedParent, generation) {
            if (failedParent === loader && generation === loader.qmlLoadGeneration) {
                loader.loadFailed = true
            }
        }
    }

    onWidthChanged: resizeLoadedItem()
    onHeightChanged: resizeLoadedItem()
    function resizeLoadedItem() {
        if (!item) { return }
        item.width = width
        item.height = height
    }

    function load(newSource, callback) {
        var generation = ++qmlLoadGeneration
        loadFailed = false
        if (item) { item.destroy(); item = null }
        source = newSource
        if (source === "") {
            screenChanged("Closed", "")
            return
        }
        surface.load(newSource, loader, function(newItem) {
            if (generation !== loader.qmlLoadGeneration) {
                if (newItem) { newItem.destroy() }
                return
            }
            if (!newItem) { loader.loadFailed = true; return }
            loader.loadFailed = false
            loader.item = newItem
            if (newItem.hasOwnProperty("tabletNavigationProvided")) {
                newItem.tabletNavigationProvided = loader.sharedTouchNavigation
            }
            loader.resizeLoadedItem()
            loader.loaded()
            if (newItem.hasOwnProperty("sendToScript")) {
                newItem.sendToScript.connect(loader.sendToScript)
            }
            if (newItem.hasOwnProperty("setRootMenu")) {
                newItem.setRootMenu(loader.rootMenu, loader.subMenu)
            }
            if (callback) { callback() }
            // Qt 5 and Qt 6 native hosts differ in when completeCreate happens.
            // Defer focus for both so it never races component completion.
            Qt.callLater(function() {
                if (loader.item === newItem) { newItem.forceActiveFocus() }
            })
            var type = "QML"
            if (newSource === "hifi/tablet/TabletHome.qml") { type = "Home" }
            else if (newSource === "hifi/tablet/TabletMenu.qml") { type = "Menu" }
            else if (newSource === "hifi/tablet/TabletWebView.qml") { return }
            loader.screenChanged(type, newSource)
        })
    }
}
