// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Controls 2.3
import QtTest 1.2

TestCase {
    id: testCase
    name: "NativeScriptsAssets"
    width: 360; height: 760
    visible: true
    property var selectedUrls: []
    when: windowShown
    function production(path) {
        var component = Qt.createComponent(String(ProductionRoot) + path);
        compare(component.status, Component.Ready, component.errorString());
        var object = createTemporaryObject(component, testCase, {width:360,height:760});
        verify(object !== null, component.errorString());
        wait(40);
        return object;
    }
    function control(root, name) {var found = findChild(root,name);verify(found !== null,name);return found;}
    function click(root, name) {wait(30);var item=control(root,name);verify(item.visible && item.enabled,name+" visible="+item.visible+" enabled="+item.enabled+" size="+item.width+"x"+item.height);mouseClick(item,item.width/2,item.height/2);wait(20);}
    function initTestCase() {TestServices.bindSurface(testCase);}
    function init() {TestServices.reset(); selectedUrls = [];}
    function cleanup() {TestServices.removePicker();}
    function test_actualAssetMenuAndDesktopTabletRoutes() {
        var routes = TestServices.exerciseAssetMenuRoutes();
        verify(routes.readable); verify(routes.desktop); verify(routes.tabletOnce);
    }
    function test_documentRequestPermissionsLimitsAndLifetime() {
        var result = TestServices.exerciseDocumentBoundaries();
        verify(result.busy); verify(result.staleIgnored); verify(result.distinctIds);
        compare(result.selected, 1); compare(result.failed, 3);
        compare(result.canceledRequests, 1); compare(result.canceledLeases, 2);
        verify(result.retained);
    }
    function test_desktopCompatibilityWrappers() {
        var scripts = production("hifi/dialogs/RunningScripts.qml");
        var tree = control(scripts, "scriptTree");
        tree.toggle(0); tree.selectRow(1, false);
        click(scripts, "scriptLoadSelected");
        compare(TestServices.scriptCalls.length, 1);
        scripts.destroy(); wait(30);
        var assets = production("hifi/AssetServer.qml");
        tree = control(assets, "assetTree"); tree.toggle(0); tree.selectRow(2, false);
        click(assets, "assetImport"); compare(TestServices.entityCalls.length, 1);
        assets.destroy(); wait(30);
        var browser = production("dialogs/FileDialog.qml");
        verify(control(browser, "systemDocumentPicker").enabled);
        browser.dir = "file://" + TestServices.fixtureDirectory;
        browser.selectedFile.connect(function(url){testCase.selectedUrls=[url];});
        control(browser,"fileNameInput").text="ordinary.js";
        click(browser,"fileAccept");
        compare(selectedUrls.length,1); compare(String(selectedUrls[0]),"file://"+TestServices.fixtureFile);
    }
    function test_scriptLifecycleAndNativeTree() {
        var scripts=production("hifi/dialogs/TabletRunningScripts.qml");
        var tree=control(scripts,"scriptTree");
        compare(tree.rows.length,1);
        mouseClick(control(scripts,"nativeTreeRow0"),12,24);compare(tree.rows.length,2);
        mouseClick(control(scripts,"nativeTreeRow1"),100,24);click(scripts,"scriptLoadSelected");
        compare(TestServices.scriptCalls.length,1);compare(TestServices.scriptCalls[0].url,"https://example.invalid/ordinary.js");
        click(scripts,"scriptReloadAll");click(scripts,"scriptStopAll");
        compare(TestServices.scriptCalls.length,3);
        verify(TestServices.scriptCalls[1].restart);verify(!TestServices.scriptCalls[2].restart);
        verify(TestServices.scriptCalls.every(function(call){return call.url!=="https://example.invalid/defaultScripts.js";}));
        click(scripts,"scriptFromUrl");click(scripts,"scriptFromFile");
        compare(TestServices.urlDialogCount,1);compare(TestServices.fileDialogCount,1);
        TestServices.loadError();verify(scripts.status.indexOf("Failed to load")===0);
        tree.filterText="ordinary";wait(20);compare(tree.rows.length,2);
        tree.filterText="absent";wait(20);compare(tree.rows.length,0);
        TestServices.developer(true);scripts.developerMenuEnabled=true;click(scripts,"scriptLoadDefaults");
        compare(TestServices.scriptCalls[3].url,"https://example.invalid/defaults/defaultScripts.js");
    }
    function test_readOnlyBrowseImageModelImportAndFailure() {
        var assets=production("hifi/dialogs/TabletAssetServer.qml");
        var tree=control(assets,"assetTree");tree.toggle(0);compare(tree.rows.length,3);
        verify(!control(assets,"assetUpload").enabled);
        tree.selectRow(2,false);click(assets,"assetImport");
        compare(TestServices.entityCalls.length,1);compare(TestServices.entityCalls[0].kind,"image");
        compare(TestServices.entityCalls[0].position, {x:1, y:2, z:1});
        compare(String(TestServices.entityCalls[0].lastEditedBy), "{11111111-2222-3333-4444-555555555555}");
        verify(TestServices.entityCalls[0].collisionless); verify(!TestServices.entityCalls[0].dynamic);
        verify(assets.status.indexOf("Added")===0);
        TestServices.denyImport(true);click(assets,"assetImport");verify(assets.status.indexOf("Import failed")===0);
        TestServices.denyImport(false);tree.selectRow(1,false);click(assets,"assetImport");
        var url=control(assets,"assetModelUrl");url.forceActiveFocus();wait(20);verify(TestServices.keyboardRaised);
        keyClick(Qt.Key_Escape);tryVerify(function(){return !TestServices.keyboardRaised;});
        click(assets,"assetImport");
        var confirm = control(assets,"modelDialog").standardButton(Dialog.Ok);
        mouseClick(confirm, confirm.width/2, confirm.height/2); wait(30);
        compare(TestServices.entityCalls.length,3); compare(TestServices.entityCalls[2].kind,"model");
        compare(TestServices.entityCalls[2].position, {x:1, y:2, z:1});
        compare(TestServices.entityCalls[2].shape,"simple-compound");
        TestServices.permissions(false,false);verify(!control(assets,"assetImport").enabled);
        assets.doDeleteFile(["/models/scene.fbx"]);compare(TestServices.assetCalls.length,0);
    }
    function test_assetMutationsErrorsAndPermissionRevocation() {
        TestServices.permissions(true,true);
        var assets=production("hifi/dialogs/TabletAssetServer.qml");var tree=control(assets,"assetTree");tree.toggle(0);tree.selectRow(1,false);
        assets.doRenameFile("/models/scene.fbx","/models/renamed.fbx");compare(TestServices.assetCalls[0].kind,"rename");
        assets.setMapping("/new.fbx","a".repeat(64));compare(TestServices.assetCalls[1].kind,"mapping");
        assets.setBakingEnabled(false);compare(TestServices.assetCalls[2].kind,"baking");
        assets.doDeleteFile(["/models/scene.fbx"]);compare(TestServices.assetCalls[3].kind,"delete");
        assets.uploadFile("file://"+TestServices.fixtureFile,false);compare(TestServices.assetCalls[4].kind,"upload");
        compare(TestServices.assetCalls[4].mapping,"/models/ordinary.js");
        TestServices.backendError("permission changed");assets.doDeleteFile(["/models/scene.fbx"]);verify(assets.status.indexOf("failed")!==-1);
        TestServices.permissions(false,true);assets.doRenameFile("/models/scene.fbx","/later.fbx");compare(TestServices.assetCalls.length,6);
    }
    function test_nativeModelChangesAndSurfaceCleanup() {
        TestServices.permissions(true,true);
        var assets=production("hifi/dialogs/TabletAssetServer.qml");
        var tree=control(assets,"assetTree");tree.toggle(0);tree.selectRow(1,false);
        verify(TestServices.assetRefreshEnabled());
        TestServices.assetBakingState("Not Baked");wait(30);
        var baking=control(assets,"assetBaking");verify(baking.enabled);verify(!baking.checked);
        mouseClick(baking,baking.width/2,baking.height/2);wait(30);
        compare(TestServices.assetCalls.length,1);verify(TestServices.assetCalls[0].enabled);
        TestServices.resetAssetModel();wait(30);
        compare(tree.rows.length,0);compare(assets.selectedItemCount,0);compare(assets.selectedUrl,"");
        verify(!control(assets,"assetImport").enabled);
        assets.destroy();wait(30);verify(!TestServices.assetRefreshEnabled());
    }
    function test_popupKeyboardFieldsAndCancel() {
        TestServices.permissions(true,true);
        var assets=production("hifi/dialogs/TabletAssetServer.qml");var tree=control(assets,"assetTree");tree.toggle(0);tree.selectRow(1,false);
        click(assets,"assetRename");var field=control(assets,"assetRenamePath");field.forceActiveFocus();wait(20);verify(TestServices.keyboardRaised);keyClick(Qt.Key_A);keyClick(Qt.Key_Escape);tryVerify(function(){return !TestServices.keyboardRaised;});
        click(assets,"assetMapping");field=control(assets,"assetMappingHash");field.forceActiveFocus();wait(20);verify(TestServices.keyboardRaised);keyClick(Qt.Key_A);keyClick(Qt.Key_Escape);tryVerify(function(){return !TestServices.keyboardRaised;});
        TestServices.keyboard3D(false);click(assets,"assetRename");field=control(assets,"assetRenamePath");field.forceActiveFocus();wait(40);
        var dialog = control(assets, "renameDialog");
        var keyboard=control(dialog,"keyboard");verify(keyboard.raised);verify(keyboard.visible);verify(keyboard.parent.scale<=1);
        var before = field.text;
        keyboard.forEachKey(function(key) { if (key.glyph === "q") mouseClick(key.mouseArea, key.width/2, key.height/2); });
        compare(field.text, before + "q");
        verify(dialog.y >= 0 && dialog.y + dialog.height <= assets.height + 1);
        keyClick(Qt.Key_Escape);tryVerify(function(){return !keyboard.raised;});
    }
    function fileRow(browser, name) {
        for (var i=0; i<browser.model.count; ++i) if (browser.model.get(i,"fileName") === name) return i;
        return -1;
    }
    function test_localBrowserNavigationFilterSelectionAndSave() {
        var browser=production("dialogs/TabletFileDialog.qml");
        browser.dir="file://"+TestServices.fixtureDirectory;
        tryVerify(function(){return fileRow(browser,"ordinary.js") >= 0;});
        var nested=fileRow(browser,"nested"); verify(nested >= 0);
        click(browser,"fileRow"+nested);
        tryVerify(function(){return String(browser.dir).endsWith("/nested");});
        click(browser,"fileBack");
        tryVerify(function(){return fileRow(browser,"ordinary.js") >= 0;});
        browser.filter="Scripts (*.js)"; wait(50);
        verify(fileRow(browser,"ordinary.js")>=0);
        var sort=control(browser,"fileSort"); sort.currentIndex=2; wait(30);
        browser.selectedFiles.connect(function(urls){testCase.selectedUrls=urls;});
        click(browser,"fileRow"+fileRow(browser,"ordinary.js")); click(browser,"fileAccept");
        compare(selectedUrls.length,1);compare(String(selectedUrls[0]),"file://"+TestServices.fixtureFile);
        selectedUrls=[];
        browser=production("dialogs/NativeFileBrowser.qml");
        browser.dir="file://"+TestServices.fixtureDirectory;browser.saveDialog=true;browser.filter="Scripts (*.js)";
        browser.selectedFiles.connect(function(urls){testCase.selectedUrls=urls;});
        control(browser,"fileNameInput").text="ordinary.js";click(browser,"fileAccept");
        var confirm=control(browser,"fileOverwriteDialog").standardButton(Dialog.No);
        mouseClick(confirm,confirm.width/2,confirm.height/2);wait(30);verify(!browser.closing);compare(selectedUrls.length,0);
        control(browser,"fileNameInput").text="new-script";click(browser,"fileAccept");
        compare(selectedUrls.length,1);verify(String(selectedUrls[0]).endsWith("/new-script.js"));
    }
    function test_realFolderBrowserSystemPickerAndOldCallbacks() {
        var browser=production("dialogs/NativeFileBrowser.qml");browser.dir="file://"+TestServices.fixtureDirectory;browser.selectedFiles.connect(function(urls){testCase.selectedUrls=urls;});wait(100);
        verify(browser.model.count>=2);TestServices.installPicker();click(browser,"systemDocumentPicker");verify(browser.requestId.length>0);
        TestServices.completePicker(true);wait(30);verify(browser.error.indexOf("readable local file")!==-1);verify(!browser.closing);
        click(browser,"systemDocumentPicker");var oldId=browser.requestId;
        browser.helper.cancelDocuments(oldId);wait(20);verify(TestServices.pickerCanceled);verify(!browser.requestId);
        TestServices.completePicker();wait(20);verify(!browser.closing);
        click(browser,"systemDocumentPicker");TestServices.completePicker();wait(30);compare(selectedUrls.length,1);compare(String(selectedUrls[0]),"file://"+TestServices.fixtureFile);
    }
    function test_actualDesktopPickerAndLocalFileSelection() {
        var browser=production("dialogs/NativeFileBrowser.qml");browser.dir="file://"+TestServices.fixtureDirectory;browser.selectedFiles.connect(function(urls){testCase.selectedUrls=urls;});
        click(browser,"systemDocumentPicker");verify(browser.requestId.length>0);verify(TestServices.selectDesktopFile());wait(40);compare(selectedUrls.length,1);compare(String(selectedUrls[0]),"file://"+TestServices.fixtureFile);
        // The production QFileDialog and helper complete into this QML listener;
        // mobile provider UI is a separate adapter/device boundary.
    }
}
