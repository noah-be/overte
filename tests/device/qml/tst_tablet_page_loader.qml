import QtQuick 2.12
import QtTest 1.2
import "../../../interface/resources/qml/hifi/tablet" as TabletUi

TestCase {
    id: testCase
    name: "TabletPageLoading"
    when: windowShown
    visible: true
    width: 768
    height: 900
    QtObject {
        id: fakeSurface
        property var requests: []
        signal qmlLoadFailed(var parent, int generation)
        function load(source, parent, callback) {
            requests.push({source: source, parent: parent, callback: callback,
                generation: parent.qmlLoadGeneration})
        }
    }
    Component {
        id: pageComponent
        Item { property bool tabletNavigationProvided: false; signal sendToScript(var message) }
    }
    Component {
        id: loaderComponent
        TabletUi.TabletPageLoader { surface: fakeSurface; width: 600; height: 700; sharedTouchNavigation: true }
    }
    SignalSpy { id: screenSpy }
    SignalSpy { id: messageSpy }

    function init() { fakeSurface.requests = [] }
    function cleanup() { screenSpy.target = null; messageSpy.target = null }
    function complete(index) {
        var request = fakeSurface.requests[index]
        var page = pageComponent.createObject(request.parent)
        request.callback(page)
        return page
    }
    function test_failureAndRecovery() {
        var loader = createTemporaryObject(loaderComponent, testCase)
        loader.load("hifi/Pal.qml")
        compare(loader.item, null)
        fakeSurface.qmlLoadFailed(loader, fakeSurface.requests[0].generation)
        compare(loader.loadFailed, true)
        var home = findChild(loader, "tablet.load-error.home")
        verify(home.visible)
        loader.load("hifi/tablet/TabletHome.qml")
        screenSpy.target = loader
        screenSpy.signalName = "screenChanged"
        screenSpy.clear()
        var page = complete(1)
        compare(loader.item, page)
        compare(page.width, 600)
        compare(page.height, 700)
        compare(page.tabletNavigationProvided, true)
        compare(loader.loadFailed, false)
        compare(screenSpy.signalArguments[0][0], "Home")
        verify(!home.visible)
        loader.height = 400
        compare(page.height, 400)
        messageSpy.target = loader
        messageSpy.signalName = "sendToScript"
        messageSpy.clear()
        page.sendToScript({type: "ready"})
        compare(messageSpy.count, 1)
    }
    function test_staleResultsCannotReplaceCurrentPage() {
        var loader = createTemporaryObject(loaderComponent, testCase)
        loader.load("first.qml")
        loader.load("second.qml")
        var page = complete(1)
        complete(0)
        fakeSurface.qmlLoadFailed(loader, fakeSurface.requests[0].generation)
        compare(loader.item, page)
        compare(loader.loadFailed, false)
        loader.load("")
        compare(loader.item, null)
        compare(fakeSurface.requests.length, 2)
        fakeSurface.qmlLoadFailed(loader, fakeSurface.requests[1].generation)
        compare(loader.loadFailed, false)
    }
}
