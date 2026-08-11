import QtQuick 2.12
import QtTest 1.2
import Hifi 1.0

TestCase {
    name: "PhoneAddressBar"
    width: 900
    height: 500

    property var dialog: null
    property var backend: null
    property var field: null
    property var errorText: null

    Item {
        id: host
        anchors.fill: parent
    }

    function init() {
        DialogsManager.reset()
        AddressManager.reset()
        var path = Qt.resolvedUrl(
            "../../../../interface/resources/qml/+android_phoneInterface/AddressBarDialog.qml")
        var component = Qt.createComponent(path)
        compare(component.status, Component.Ready, component.errorString())
        dialog = component.createObject(host)
        verify(dialog !== null, component.errorString())
        backend = findChild(dialog, "FakeAddressBackend")
        field = findChild(dialog, "PhoneAddressField")
        errorText = findChild(dialog, "PhoneAddressError")
        verify(backend !== null)
        verify(field !== null)
        verify(errorText !== null)
    }

    function cleanup() {
        if (dialog) {
            dialog.destroy()
        }
        dialog = null
        backend = null
        field = null
        errorText = null
    }

    function test_initializesFromCurrentAddressAndObservesVisibility() {
        compare(field.text, "hifi://initial")
        compare(field.maximumLength, 4096)
        compare(dialog.maximumAddressLength, 4096)
        compare(backend.lastObservedShown, true)
        verify(backend.observeCount >= 1)
    }

    function test_accessibilitySemanticsCoverEveryInteractiveControl() {
        compare(field.Accessible.role, Accessible.EditableText)
        compare(field.Accessible.name, "Destination address")
        verify(field.Accessible.description.length > 0)
        verify(field.activeFocusOnTab)

        var expected = [
            ["PhoneAddressBackButton", "Back"],
            ["PhoneAddressHomeButton", "Home"],
            ["PhoneAddressGoButton", "Go"],
            ["PhoneAddressCancelButton", "Cancel"]
        ]
        for (var i = 0; i < expected.length; ++i) {
            var button = findChild(dialog, expected[i][0])
            verify(button !== null)
            compare(button.Accessible.role, Accessible.Button)
            compare(button.Accessible.name, expected[i][1])
            verify(button.Accessible.description.length > 0)
            verify(button.activeFocusOnTab)
        }
        compare(errorText.Accessible.role, Accessible.StaticText)
    }

    function test_keyboardFocusStartsOnDestinationField() {
        dialog.shown = false
        dialog.shown = true
        wait(0)
        verify(field.focus)
    }

    function test_validAddressIsTrimmedLoadedAndClosed() {
        field.text = "  overte://example.com/place  "
        dialog.goToAddress()
        compare(backend.loadAddressCount, 1)
        compare(backend.lastAddress, "overte://example.com/place")
        compare(DialogsManager.hideAddressBarCount, 1)
    }

    function test_emptyAndControlAddressesAreRejectedAndFieldBoundsInput() {
        field.text = "   "
        dialog.goToAddress()
        wait(0)
        compare(backend.loadAddressCount, 0)
        compare(DialogsManager.hideAddressBarCount, 0)
        verify(errorText.text.length > 0)

        field.text = "overte://bad\npath"
        dialog.goToAddress()
        wait(0)
        compare(backend.loadAddressCount, 0)
        compare(DialogsManager.hideAddressBarCount, 0)
        verify(errorText.text.length > 0)

        field.text = Array(dialog.maximumAddressLength + 2).join("x")
        compare(field.text.length, dialog.maximumAddressLength)
        dialog.goToAddress()
        wait(0)
        compare(backend.loadAddressCount, 1)
        compare(backend.lastAddress.length, dialog.maximumAddressLength)
        compare(DialogsManager.hideAddressBarCount, 1)
        compare(errorText.text, "")
    }

    function test_shownStateIsForwardedAndCloseUsesDialogsManager() {
        dialog.shown = false
        compare(backend.lastObservedShown, false)
        dialog.shown = true
        compare(backend.lastObservedShown, true)

        dialog.closeDialog()
        compare(DialogsManager.hideAddressBarCount, 1)
    }

    function test_reshowRestoresCurrentAddressAndClearsError() {
        field.text = "\u007f"
        dialog.goToAddress()
        wait(0)
        verify(errorText.text.length > 0)

        AddressManager.href = "overte://restored/place"
        dialog.shown = false
        dialog.shown = true
        wait(0)
        compare(field.text, "overte://restored/place")
        compare(errorText.text, "")
        compare(backend.observeCount, 3)
    }

    function test_backendHostChangeClosesDialog() {
        backend.hostChanged()
        compare(DialogsManager.hideAddressBarCount, 1)
    }

    function test_backHomeGoAndCancelActionsUseBackendContract() {
        var back = findChild(dialog, "PhoneAddressBackButton")
        var home = findChild(dialog, "PhoneAddressHomeButton")
        var go = findChild(dialog, "PhoneAddressGoButton")
        var cancel = findChild(dialog, "PhoneAddressCancelButton")
        verify(back !== null)
        verify(home !== null)
        verify(go !== null)
        verify(cancel !== null)

        back.androidClickAction()
        compare(backend.loadBackCount, 1)
        compare(DialogsManager.hideAddressBarCount, 1)

        home.androidClickAction()
        compare(backend.loadHomeCount, 1)
        compare(DialogsManager.hideAddressBarCount, 2)

        field.text = "overte://button"
        go.androidClickAction()
        compare(backend.lastAddress, "overte://button")
        compare(DialogsManager.hideAddressBarCount, 3)

        cancel.androidClickAction()
        compare(DialogsManager.hideAddressBarCount, 4)
    }
}
