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
        function test_typedPropertiesUseRealPointerAndNestedValues() {
            page.currentTab = 2
            requests.clear()
            page.fromScript({ method: "nativeCreate.selection", params: { entities: [{
                id: "model-typed", type: "Model", editable: true, properties: {
                    name: "Model", modelURL: "https://example.test/old.fbx",
                    animation: { fps: 30, running: false }, voxelData: "opaque compressed data"
                } }] } })
            var search = findChild(page, "NativeCreatePropertySearch")
            search.text = "modelURL"
            wait(20)
            click("NativeCreateProperty_modelURL")
            var url = findChild(page, "NativeCreateProperty_modelURL")
            url.selectAll()
            keyClick(Qt.Key_N)
            keyClick(Qt.Key_E)
            keyClick(Qt.Key_W)
            click("NativeCreateApply")
            compare(last().params.properties.modelURL, "new")

            search.text = "animation.running"
            wait(20)
            click("NativeCreateFlag_animation.running")
            click("NativeCreateApply")
            compare(last().params.properties.animation.running, true)
            compare(last().params.properties.animation.fps, 30)

            search.text = "animation.fps"
            wait(20)
            click("NativeCreateProperty_animation.fps")
            page.fromScript({ method: "picoAdjustFocusedNumber", params: { direction: 1 } })
            compare(last().method, "nativeCreate.preview")
            compare(last().params.properties.animation.fps, 30.01)
            compare(last().params.properties.animation.running, true)
            verify(page.typedFieldRows.every(function(row) { return row.path !== "voxelData" }))
        }
        function test_voxelControlsUseRealPointerEvents() {
            page.currentTab = 3
            page.fromScript({ method: "nativeCreate.settings", params: {
                createAppMode: "voxel", voxelEditMode: "sphere", voxelRemove: false,
                voxelSphereSize: 0.3, voxelBrushLength: 0.5,
                voxelEditDynamics: "click", voxelPointerMode: "laser"
            } })
            requests.clear()
            click("NativeCreateVoxelRemove")
            compare(last().method, "nativeCreate.settings")
            compare(last().params.voxelRemove, true)
            click("NativeCreateVoxelRemove")
            compare(last().params.voxelRemove, false)
            var diameter = findChild(page, "NativeCreateVoxelDiameter")
            click("NativeCreateVoxelDiameter")
            diameter.selectAll()
            keyClick(Qt.Key_2)
            click("NativeCreateVoxelApply")
            compare(last().params.voxelSphereSize, 2)
            compare(last().params.voxelBrushLength, 0.5)
            diameter.text = "invalid"
            requests.clear()
            click("NativeCreateVoxelApply")
            compare(requests.count, 0)
            verify(page.statusError)
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
