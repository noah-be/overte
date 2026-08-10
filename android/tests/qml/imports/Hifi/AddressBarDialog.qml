import QtQuick 2.12

Item {
    objectName: "FakeAddressBackend"
    property bool backEnabled: true
    property bool lastObservedShown: false
    property int observeCount: 0
    property int loadAddressCount: 0
    property int loadBackCount: 0
    property int loadHomeCount: 0
    property string lastAddress: ""
    signal hostChanged()

    function observeShownChanged(shown) {
        lastObservedShown = shown
        observeCount += 1
    }

    function loadAddress(address) {
        lastAddress = address
        loadAddressCount += 1
    }

    function loadBack() {
        loadBackCount += 1
    }

    function loadHome() {
        loadHomeCount += 1
    }
}
