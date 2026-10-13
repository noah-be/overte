// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtTest 1.2
import "../../qml"

Item {
    width: 480
    height: 720
    NativeCreate { id: page; anchors.fill: parent }
    SignalSpy { id: requests; target: page; signalName: "sendToScript" }
    TestCase {
        name: "NativeCreate"
        when: windowShown

        function click(name) {
            var button = findChild(page, name)
            verify(button !== null, name)
            tryVerify(function() { return button.visible && button.width > 0 && button.height > 0 })
            wait(20)
            var ancestor = button.parent
            while (ancestor) {
                if (typeof ancestor.contentY === "number" && typeof ancestor.contentHeight === "number") {
                    var y = button.mapToItem(ancestor, 0, 0).y
                    if (y < 0) { ancestor.contentY += y }
                    else if (y + button.height > ancestor.height) { ancestor.contentY += y + button.height - ancestor.height }
                    wait(20)
                }
                ancestor = ancestor.parent
            }
            mouseClick(button, button.width / 2, button.height / 2)
        }
        function last() { return requests.signalArguments[requests.count - 1][0] }
        function selection() {
            page.fromScript({ method: "nativeCreate.selection", params: { entities: [{
                id: "entity-one", type: "Shape", editable: true, properties: {
                    name: "Example", position: { x: 1, y: 2, z: 3 }, rotation: { x: 0, y: 0, z: 0 },
                    dimensions: { x: 1, y: 1, z: 1 }, color: { red: 100, green: 100, blue: 100 },
                    visible: true, dynamic: false, collisionless: false
                } }], canUndo: true, canRedo: false } })
        }
        function test_createSelectEditToolsImport() {
            requests.clear()
            click("NativeCreateNew_Shape")
            compare(last().method, "nativeCreate.create")
            compare(last().params.properties.type, "Shape")
            compare(last().params.host, "domain")

            page.fromScript({ method: "nativeCreate.list", params: {
                entities: [{ id: "entity-one", name: "Example", type: "Shape", locked: false }], selectedIDs: [] } })
            click("NativeCreateTab_1")
            wait(20)
            click("NativeCreateEntity_entity-one")
            compare(last().method, "nativeCreate.select")
            compare(last().params.ids[0], "entity-one")
            selection()
            var name = findChild(page, "NativeCreateName")
            compare(name.text, "Example")
            name.forceActiveFocus()
            name.selectAll()
            keyClick(Qt.Key_R)
            keyClick(Qt.Key_E)
            keyClick(Qt.Key_N)
            keyClick(Qt.Key_A)
            keyClick(Qt.Key_M)
            keyClick(Qt.Key_E)
            keyClick(Qt.Key_D)
            click("NativeCreateApply")
            compare(last().method, "nativeCreate.edit")
            compare(last().params.id, "entity-one")
            compare(last().params.properties.name, "renamed")

            var position = findChild(page, "NativeCreateField_position_x")
            position.forceActiveFocus()
            requests.clear()
            page.fromScript({ method: "picoAdjustFocusedNumber", params: { direction: 1 } })
            compare(last().method, "nativeCreate.preview")
            compare(last().params.properties.position.x, 1.01)
            click("NativeCreateTab_3")
            click("NativeCreateTool_grid-visible")
            compare(last().method, "nativeCreate.tool")
            compare(last().params.action, "grid-visible")

            click("NativeCreateTab_4")
            findChild(page, "NativeCreateImportUrl").text = "https://example.test/entities.json"
            click("NativeCreateImport")
            compare(last().method, "nativeCreate.import")
            compare(last().params.url, "https://example.test/entities.json")
            click("NativeCreateBrowse")
            compare(last().method, "nativeCreate.browse")
            page.fromScript({ method: "nativeCreate.status", params: { text: "Import failed", error: true } })
            compare(findChild(page, "NativeCreateStatus").text, "Import failed")
        }
        function test_narrowLayout() {
            page.width = 320
            page.height = 600
            page.currentTab = 0
            wait(20)
            var shape = findChild(page, "NativeCreateNew_Shape")
            verify(shape.width >= 100 && shape.height >= 44)
            verify(shape.mapToItem(page, 0, 0).x >= 0)
            verify(shape.mapToItem(page, shape.width, 0).x <= page.width)
            for (var i = 0; i < 5; i++) {
                var tab = findChild(page, "NativeCreateTab_" + i)
                verify(tab.width > 0 && tab.height >= 44)
                verify(tab.mapToItem(page, tab.width, 0).x <= page.width)
            }
        }
        function test_detailedCreationEntry() {
            page.currentTab = 0
            requests.clear()
            findChild(page, "NativeCreateDetailedType").currentIndex = 3
            click("NativeCreateDetailed")
            compare(last().method, "newEntityButtonClicked")
            compare(last().params.buttonName, "newPolyVoxButton")
        }
    }
}
