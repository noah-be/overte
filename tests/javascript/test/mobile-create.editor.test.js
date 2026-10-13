"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const path = require("node:path");
const { FakeSignal, createTabletApi, runProductionScript } = require("../support");

// Run the complete production editor. Only engine APIs and unrelated viewport
// helpers are substituted; property conversion, creation, import and history
// below execute the shipped edit.js and EntityListTool implementations.
function editor() {
    const base = path.resolve(__dirname, "../../../scripts/system/create");
    const signal = () => {
        const result = new FakeSignal();
        const connect = result.connect.bind(result);
        result.connect = (...args) => connect(args.at(-1));
        result.addListener = result.connect;
        return result;
    };
    const noop = () => {};
    const helper = methods => new Proxy(methods || {}, { get: (target, key) => key in target ? target[key] : noop });
    function Helper() { return helper(); }
    function CreateWindow() { return helper({ window: helper(), webEventReceived: signal(), fromQml: signal(),
        interactiveWindowHidden: signal(), isVisible: () => false }); }
    const vector = { x: 0, y: 0, z: 0 };
    const sum = (a, b) => ({ x: a.x + b.x, y: a.y + b.y, z: a.z + b.z });
    const multiply = (a, b) => typeof a === "number"
        ? { x: a * b.x, y: a * b.y, z: a * b.z }
        : { x: a.x * b, y: a.y * b, z: a.z * b };
    const world = new Map();
    const state = { nextID: 0, domain: true, avatar: true, locks: true, importOK: true,
        pasteEmpty: false, clipboardError: false, edits: [], deletes: [], mappings: new Set() };
    const Entities = helper({ canRez: () => state.domain, canRezTmp: () => false,
        canRezAvatarEntities: () => state.avatar, canAdjustLocks: () => state.locks,
        canViewAssetURLs: () => true,
        canRezChanged: signal(), canRezTmpChanged: signal(), canRezAvatarEntitiesChanged: signal(),
        canAdjustLocksChanged: signal(), canViewAssetURLsChanged: signal(), deletingEntity: signal(),
        addEntity(properties, host) {
            const id = "entity-" + ++state.nextID;
            world.set(id, { id, position: { ...vector }, registrationPoint: { x: 0.5, y: 0.5, z: 0.5 },
                dimensions: { x: 1, y: 1, z: 1 },
                rotation: { x: 0, y: 0, z: 0, w: 1 }, localRotation: { x: 0, y: 0, z: 0, w: 1 },
                parentID: "none", locked: false, visible: true, script: "", serverScripts: "",
                ...structuredClone(properties), entityHostType: host || "domain",
                owningAvatarID: host === "avatar" ? "self" : undefined });
            return id;
        },
        getEntityProperties(id) { return structuredClone(world.get(id) || {}); },
        getMultipleEntityProperties(ids) { return ids.map(id => Entities.getEntityProperties(id)); },
        findEntities: () => [...world.keys()], findEntitiesByType: () => [], getChildrenIDs: () => [],
        editEntity(id, properties) {
            state.edits.push([id, structuredClone(properties)]);
            if (world.has(id)) { Object.assign(world.get(id), structuredClone(properties)); }
            return id;
        },
        deleteEntity(id) { state.deletes.push(id); world.delete(id); },
        getServerScriptStatus(id, callback) { callback(false, false, "", ""); }
    });
    const listeners = [];
    const selection = helper({ selections: [], savedProperties: {},
        worldPosition: { ...vector }, worldDimensions: { x: 1, y: 1, z: 1 },
        addEventListener(callback) { listeners.push(callback); },
        _update(updated) { listeners.forEach(callback => callback(updated === true)); },
        setSelections(ids) { this.selections = Array.from(ids); this.saveProperties(); this._update(true); },
        clearSelections() { this.setSelections([]); },
        addEntity(id) { this.setSelections([id]); }, hasSelection() { return this.selections.length > 0; },
        hasUnlockedSelection() { return this.selections.some(id => !world.get(id)?.locked); },
        saveProperties() {
            this.savedProperties = Object.fromEntries(this.selections.map(id => [id, Entities.getEntityProperties(id)]));
        }
    });
    const Tablet = createTabletApi();
    const tablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
    tablet.toolbarMode = false;
    tablet.setLandscape = noop;
    // TabletProxy pushes into Edit.qml's stack without changing the app screen.
    tablet.pushOntoStack = source => tablet.navigation.push({ type: "stack", args: [source] });
    tablet.popFromStack = noop;
    const connect = tablet.webEventReceived.connect.bind(tablet.webEventReceived);
    tablet.webEventReceived.connect = (...args) => connect(args.at(-1));
    const ending = signal();
    const globals = {
        Script: { scriptEnding: ending, update: signal(), include: noop,
            require: filename => filename.endsWith("createWindow.js") ? CreateWindow
                : filename.endsWith("entityShapeVisualizer.js") ? function() {
                    return helper({ getLocalEntityToExclude: () => [] });
                } : require(path.resolve(base, filename)),
            resolvePath: value => path.resolve(base, value), getExternalPath: () => "https://example.test/default.png",
            ExternalPaths: { Assets: 0 }, setTimeout: () => 1, clearTimeout: noop,
            setInterval: () => 1, clearInterval: noop },
        Entities, Tablet, SelectionManager: selection,
        SelectionDisplay: helper({ getSpaceMode: () => "world" }),
        EntityIconOverlayManager: Helper, CameraManager: Helper, GridTool: Helper,
        Grid: function() { return helper({ snapToGrid: value => value, snapToSurface: value => value,
            getSnapToGrid: () => false, getOrigin: () => vector }); },
        EditTools: Helper, EditVoxels: Helper,
        Window: helper({ innerWidth: 800, innerHeight: 600, x: 0, y: 0,
            domainChanged: signal(), svoImportRequested: signal(), browseChanged: signal(), promptTextChanged: signal() }),
        HMD: { active: false, displayModeChanged: signal() },
        MyAvatar: { position: { ...vector }, orientation: { x: 0, y: 0, z: 0, w: 1 }, sessionUUID: "self", SELF_ID: "self" },
        Camera: { position: { ...vector }, orientation: { x: 0, y: 0, z: 0, w: 1 }, mode: "first person" },
        Vec3: helper({ ZERO: vector, UNIT_Z: { x: 0, y: 0, z: 1 }, sum, multiply,
            multiplyQbyV: (q, v) => v, multiplyVbyV: (a, b) => ({ x: a.x * b.x, y: a.y * b.y, z: a.z * b.z }),
            subtract: (a, b) => sum(a, multiply(-1, b)), dot: (a, b) => a.x * b.x + a.y * b.y + a.z * b.z,
            distance: () => 1, equal: (a, b) => JSON.stringify(a) === JSON.stringify(b) }),
        Quat: helper({ getForward: () => ({ x: 0, y: 0, z: -1 }), safeEulerAngles: q => ({ x: q.x, y: q.y, z: q.z }),
            fromVec3Degrees: v => ({ ...v, w: 1 }), multiply: (a, b) => b }),
        Controller: helper({ Standard: { LY: 0, LX: 1 }, Hardware: { Application: { PlatformMac: 0 }, Keyboard: {} },
            mousePressEvent: signal(), mouseMoveEvent: signal(), mouseReleaseEvent: signal(),
            keyPressEvent: signal(), keyReleaseEvent: signal(),
            newMapping: () => ({ from: () => ({ to: noop, peek: () => ({ to: noop }), when: () => ({ to: noop }) }) }),
            enableMapping: name => state.mappings.add(name), disableMapping: name => state.mappings.delete(name) }),
        Overlays: helper({ addOverlay: () => "overlay" }),
        Menu: helper({ menuItemEvent: signal(), isOptionChecked: () => false, menuExists: () => true }),
        Settings: { getValue: (key, fallback) => fallback, setValue: noop },
        Messages: helper({ messageReceived: signal() }), UserActivityLogger: helper(),
        Render: { cameraClippingEnabled: false }, Uuid: { NONE: "none", generate: () => "uuid", isNull: id => id === "none" },
        progressDialog: helper(), tooltip: helper(), audioFeedback: helper(),
        Clipboard: {
            importEntities() { if (state.clipboardError) { throw new Error("load failed"); } return state.importOK; },
            getClipboardContentsLargestDimension: () => 1,
            pasteEntities(position, host) { return state.pasteEmpty ? [] : [Entities.addEntity({
                type: "Shape", name: "Imported", position, dimensions: { x: 1, y: 1, z: 1 }
            }, host)]; }
        },
        Toolbars: helper(), Desktop: helper(), Picks: {}, print: noop, console
    };
    const listContext = runProductionScript(path.join(base, "entityList/entityList.js"), globals).context;
    globals.EntityListTool = listContext.EntityListTool;
    runProductionScript(path.join(base, "edit.js"), globals);
    const app = selection.createApp;
    tablet.buttons.find(button => button.properties.text === "CREATE").click();
    const send = (method, params = {}) => tablet.fromQml.emit({ method: "nativeCreate." + method, params });
    send("ready");
    return { app, state, world, selection, tablet, send, ending, Entities, Window: globals.Window };
}

test("native Create drives production creation, property conversion and undo/redo", () => {
    const { app, world, selection, send } = editor();
    send("create", { host: "domain", properties: { type: "Shape", name: "Original" } });
    const id = selection.selections[0];
    assert.equal(world.get(id).type, "Shape");
    assert.equal(app.undoHistory.history.length, 1);
    send("edit", { id, properties: { name: "Renamed", rotation: { x: 10, y: 20, z: 30 }, dynamic: false } });
    assert.equal(world.get(id).name, "Renamed");
    assert.equal(world.get(id).rotation.w, 1);
    assert.deepEqual(world.get(id).localVelocity, { x: 0, y: 0, z: 0 });
    assert.equal(app.undoHistory.history.length, 2);
    send("tool", { action: "undo" });
    assert.equal(world.get(id).name, "Original");
    send("tool", { action: "redo" });
    assert.equal(world.get(id).name, "Renamed");
});

test("the native app retains the existing detailed creation dialog handlers", () => {
    const { world, selection, tablet } = editor();
    tablet.fromQml.emit({ method: "newEntityButtonClicked", params: { buttonName: "newMaterialButton" } });
    assert.equal(tablet.navigation.at(-1).type, "stack");
    assert.match(tablet.navigation.at(-1).args[0], /NewMaterialDialog.qml$/);
    tablet.fromQml.emit({ method: "newMaterialDialogAdd", params: { textInput: "materialData" } });
    assert.equal(world.get(selection.selections[0]).type, "Material");
    assert.equal(world.get(selection.selections[0]).materialURL, "materialData");
});

test("avatar-only permissions do not authorize a legacy domain creation dialog", () => {
    const { state, world, tablet, send } = editor();
    state.domain = false;
    tablet.fromQml.emit({ method: "newMaterialDialogAdd", params: { textInput: "materialData" } });
    assert.equal(world.size, 0);
    send("create", { properties: { type: "Shape" }, host: "avatar" });
    assert.equal(world.size, 1);
    assert.equal([...world.values()][0].entityHostType, "avatar");
});

test("native import executes Clipboard placement, reports failure and records real history", () => {
    const { app, state, world, selection, tablet, send } = editor();
    const status = () => tablet.qmlMessages.filter(message => message.method === "nativeCreate.status").at(-1).params;
    state.pasteEmpty = true;
    send("import", { url: "https://example.test/entities.json" });
    assert.equal(status().error, true);
    assert.equal(app.undoHistory.history.length, 0);
    state.pasteEmpty = false;
    send("import", { url: "https://example.test/entities.json", position: { x: 4, y: 5, z: 6 } });
    const id = selection.selections[0];
    assert.deepEqual(world.get(id).position, { x: 4, y: 5, z: 6 });
    assert.equal(status().error, false);
    assert.equal(app.undoHistory.history.length, 1);
    send("tool", { action: "undo" });
    assert.equal(world.has(id), false);
    send("tool", { action: "redo" });
    assert.equal([...world.values()].some(entity => entity.name === "Imported"), true);
    state.clipboardError = true;
    send("import", { url: "atp:/failed.json" });
    assert.equal(status().error, true);
    state.clipboardError = false;
    send("import", { url: "atp:/avatar.json", host: "avatar" });
    assert.equal(status().error, false);
    assert.equal(world.get(selection.selections[0]).entityHostType, "avatar");
    send("tool", { action: "undo" });
    send("tool", { action: "redo" });
    assert.equal(world.get(selection.selections[0]).entityHostType, "avatar");
});

test("native delete uses the existing editor and undo preserves avatar ownership", () => {
    const { world, selection, send } = editor();
    send("create", { properties: { type: "Shape", name: "Avatar shape" }, host: "avatar" });
    const id = selection.selections[0];
    send("tool", { action: "delete" });
    assert.equal(world.has(id), false);
    send("tool", { action: "undo" });
    assert.equal(world.get(selection.selections[0]).name, "Avatar shape");
    assert.equal(world.get(selection.selections[0]).entityHostType, "avatar");
    assert.equal(world.get(selection.selections[0]).owningAvatarID, "self");
});

test("avatar creation redo uses the original entity host instead of the domain default", () => {
    const { world, selection, send } = editor();
    send("create", { properties: { type: "Shape", name: "Avatar create" }, host: "avatar" });
    send("tool", { action: "undo" });
    assert.equal(world.size, 0);
    send("tool", { action: "redo" });
    assert.equal(world.get(selection.selections[0]).entityHostType, "avatar");
    assert.equal(world.get(selection.selections[0]).owningAvatarID, "self");
});

test("permission revocation deactivates native Create without retaining focused controls", () => {
    const { state, Entities, tablet, send } = editor();
    send("create", { properties: { type: "Shape" } });
    send("numericFocus", { focused: true });
    state.domain = state.avatar = false;
    Entities.canRezChanged.emit(false);
    assert.equal(state.mappings.size, 0);
    assert.equal(tablet.navigation.at(-1).type, "home");
});

test("host-specific permission loss blocks history while other Create permissions remain", () => {
    const { app, state, world, selection, Entities, tablet, send } = editor();
    send("create", { properties: { type: "Shape" }, host: "avatar" });
    const id = selection.selections[0];
    state.avatar = false;
    Entities.canRezAvatarEntitiesChanged.emit(false);
    const update = tablet.qmlMessages.filter(message => message.method === "nativeCreate.selection").at(-1);
    assert.equal(update.params.entities[0].editable, false);
    send("tool", { action: "undo" });
    assert.equal(app.undoHistory.lastExecutedIndex, 0);
    assert.equal(world.has(id), true);
});

test("numeric preview commits one history operation and cleanup retires input and messages", () => {
    const { app, state, world, selection, tablet, send, ending } = editor();
    send("create", { properties: { type: "Shape" } });
    const id = selection.selections[0];
    const original = structuredClone(world.get(id).position);
    send("numericFocus", { focused: true });
    send("preview", { id, properties: { position: { x: 3, y: 2, z: 1 } } });
    send("preview", { id, properties: { position: { x: 4, y: 2, z: 1 } } });
    assert.equal(app.undoHistory.history.length, 1);
    send("numericFocus", { focused: false });
    assert.equal(app.undoHistory.history.length, 2);
    send("tool", { action: "undo" });
    assert.deepEqual(world.get(id).position, original);
    send("numericFocus", { focused: true });
    send("browse");
    ending.emit();
    assert.equal(state.mappings.size, 0);
    assert.equal(tablet.fromQml.listenerCount, 0);
    send("edit", { id, properties: { name: "After cleanup" } });
    assert.notEqual(world.get(id).name, "After cleanup");
});
