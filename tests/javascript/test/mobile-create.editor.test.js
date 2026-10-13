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
        result.removeListener = result.disconnect.bind(result);
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
    const timers = new Map();
    const routes = new Map();
    const state = { nextID: 0, domain: true, avatar: true, locks: true, importOK: true,
        pasteEmpty: false, clipboardError: false, edits: [], deletes: [], mappings: new Set(),
        voxelWrites: [], pendingVoxels: {}, controllerValid: false, pickID: null, pickPoint: { x: 1, y: 1, z: 1 },
        poll(count = 1) { for (let i = 0; i < count; i++) { [...timers.values()].forEach(callback => callback()); } },
        compress() { Object.entries(this.pendingVoxels).forEach(([id, value]) => { world.get(id).voxelData = value; }); this.pendingVoxels = {}; },
        route(input, value) { routes.get(input)(value); }
    };
    const voxelWrite = (kind, id, ...args) => {
        state.voxelWrites.push({ kind, id, args });
        state.pendingVoxels[id] = "compressed-" + state.voxelWrites.length;
        return true;
    };
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
        getServerScriptStatus(id, callback) { callback(false, false, "", ""); },
        worldCoordsToVoxelCoords: (id, value) => value, voxelCoordsToWorldCoords: (id, value) => value,
        setVoxel: (id, ...args) => voxelWrite("single", id, ...args),
        setVoxelSphere: (id, ...args) => voxelWrite("sphere", id, ...args),
        setVoxelsInCuboid: (id, ...args) => voxelWrite("cube", id, ...args),
        isVoxelDataReady: id => world.has(id) && !(id in state.pendingVoxels),
        findRayIntersection: () => ({ intersects: true, entityID: state.pickID, intersection: state.pickPoint })
    });
    const listeners = [];
    const selection = helper({ selections: [], savedProperties: {},
        pointingAtTabletLeft: false, pointingAtTabletRight: false,
        pointingAtDesktopWindowLeft: false, pointingAtDesktopWindowRight: false,
        worldPosition: { ...vector }, worldDimensions: { x: 1, y: 1, z: 1 },
        addEventListener(callback) { listeners.push(callback); },
        _update(updated) { listeners.forEach(callback => callback(updated === true)); },
        setSelections(ids) { this.selections = Array.from(ids); this.saveProperties(); this._update(true); },
        clearSelections() { this.setSelections([]); },
        addEntity(id) { this.setSelections([id]); }, hasSelection() { return this.selections.length > 0; },
        hasUnlockedSelection() { return this.selections.some(id => !world.get(id)?.locked); },
        saveProperties() {
            this.savedProperties = Object.fromEntries(this.selections.map(id => [id, Entities.getEntityProperties(id)]));
        },
        updateEditSettings(data) { if (data.createAppMode === "voxel") { selection.clearSelections(); } }
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
            resourcesPath: () => "resources/",
            setInterval(callback) { const id = {}; timers.set(id, callback); return id; },
            clearInterval: id => timers.delete(id) },
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
        Camera: { position: { ...vector }, orientation: { x: 0, y: 0, z: 0, w: 1 }, mode: "first person",
            computePickRay: () => ({ origin: { ...vector }, direction: { x: 0, y: 0, z: 1 } }) },
        Vec3: helper({ ZERO: vector, UNIT_Z: { x: 0, y: 0, z: 1 }, sum, multiply,
            multiplyQbyV: (q, v) => v, multiplyVbyV: (a, b) => ({ x: a.x * b.x, y: a.y * b.y, z: a.z * b.z }),
            subtract: (a, b) => sum(a, multiply(-1, b)), dot: (a, b) => a.x * b.x + a.y * b.y + a.z * b.z,
            distance: () => 1, normalize: v => v, equal: (a, b) => JSON.stringify(a) === JSON.stringify(b),
            toPolar: () => ({ x: 0.5, y: 0.25, z: 0 }), fromPolar: (x, y) => ({ x, y, z: 1 }) }),
        Quat: helper({ getForward: () => ({ x: 0, y: 0, z: -1 }), getUp: () => ({ x: 0, y: 0, z: 1 }),
            safeEulerAngles: q => ({ x: q.x, y: q.y, z: q.z }),
            fromVec3Degrees: v => ({ ...v, w: 1 }), multiply: (a, b) => b }),
        Controller: helper({ Standard: { LY: 0, LX: 1, RTClick: 2, LTClick: 3, RT: 4, LT: 5,
            LeftHand: 6, RightHand: 7, LeftGrip: 8, RightGrip: 9 }, Hardware: { Application: { PlatformMac: 0 }, Keyboard: {} },
            mousePressEvent: signal(), mouseMoveEvent: signal(), mouseReleaseEvent: signal(),
            keyPressEvent: signal(), keyReleaseEvent: signal(),
            newMapping: name => ({ enable: () => state.mappings.add(name), disable: () => state.mappings.delete(name),
                from: input => ({ to: callback => routes.set(input, callback),
                    peek: () => ({ to: callback => routes.set(input, callback) }), when: () => ({ to: noop }) }) }),
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
        SoundCache: { getSound: () => ({}) }, Audio: helper(),
        getControllerWorldLocation: hand => ({ valid: hand >= 0 && state.controllerValid,
            translation: { ...vector }, rotation: { x: 0, y: 0, z: 0, w: 1 } }),
        TRIGGER_ON_VALUE: 0.5,
        Toolbars: helper(), Desktop: helper(), Picks: {}, print: noop, console
    };
    const listContext = runProductionScript(path.join(base, "entityList/entityList.js"), globals).context;
    globals.EntityListTool = listContext.EntityListTool;
    globals.EditTools = runProductionScript(path.join(base, "editModes/editModes.js"), globals).context.EditTools;
    globals.EditVoxels = runProductionScript(path.join(base, "editModes/editVoxels.js"), globals).context.EditVoxels;
    runProductionScript(path.join(base, "edit.js"), globals);
    const app = selection.createApp;
    tablet.buttons.find(button => button.properties.text === "CREATE").click();
    const send = (method, params = {}) => tablet.fromQml.emit({ method: "nativeCreate." + method, params });
    send("ready");
    return { app, state, world, selection, tablet, send, ending, Entities, Window: globals.Window,
        Controller: globals.Controller, frame: delta => globals.Script.update.emit(delta), timers };
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
    tablet.webEventReceived.emit(JSON.stringify({ type: "update-edit-tools", voxelRemove: true }));
    assert.equal(app.editVoxels.editTools.getSettings().voxelRemove, false);
    send("edit", { id, properties: { name: "After cleanup" } });
    assert.notEqual(world.get(id).name, "After cleanup");
});

test("native typed groups use the same emitter and key-light projection as desktop properties", () => {
    const { Entities, world, tablet, send } = editor();
    const id = Entities.addEntity({ type: "Zone", emitOrientation: { x: 10, y: 20, z: 30, w: 1 },
        keyLight: { direction: { x: 1, y: 0, z: 0 }, intensity: 2 } });
    send("refresh");
    send("select", { ids: [id] });
    const update = tablet.qmlMessages.filter(message => message.method === "nativeCreate.selection").at(-1);
    assert.equal(update.params.entities[0].properties.emitOrientation.w, undefined);
    assert.equal(update.params.entities[0].properties.keyLight.direction.x, 0.5);
    send("edit", { id, properties: { emitOrientation: { x: 1, y: 2, z: 3 },
        keyLight: { direction: { x: 0.75, y: 0.25, z: 0 }, intensity: 3 } } });
    assert.equal(world.get(id).emitOrientation.w, 1);
    assert.equal(world.get(id).keyLight.direction.z, 1);
    assert.equal(world.get(id).keyLight.intensity, 3);
});

test("native voxel settings execute real EditTools listeners and round-trip false values", () => {
    const { tablet, send } = editor();
    send("settings", { createAppMode: "voxel", voxelEditMode: "sphere", voxelRemove: true });
    send("settings", { voxelRemove: false });
    const update = tablet.qmlMessages.filter(message => message.method === "nativeCreate.settings").at(-1);
    assert.equal(update.params.voxelRemove, false);
    assert.equal(update.params.voxelEditMode, "sphere");
    assert.equal(update.params.createAppMode, "voxel");
    send("settings", { constructor: "invalid" });
    send("settings", JSON.parse('{"__proto__":"invalid"}'));
    send("settings", { voxelSphereSize: Infinity });
    assert.equal(tablet.qmlMessages.filter(message => message.method === "nativeCreate.settings").at(-1), update);
});

function volume(environment, extra = {}) {
    const id = environment.Entities.addEntity({ type: "PolyVox", name: "Volume", voxelData: "before", ...extra }, extra.entityHostType);
    environment.state.pickID = id;
    environment.send("settings", { createAppMode: "voxel" });
    return id;
}

test("real voxel ray actions wait for delayed compression and reuse production undo/redo", () => {
    const environment = editor();
    const { app, state, world, Controller, send } = environment;
    const id = volume(environment);
    Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
    Controller.mouseReleaseEvent.emit({});
    assert.equal(state.voxelWrites.length, 1);
    assert.equal(state.voxelWrites[0].kind, "single");
    state.poll(5);
    assert.equal(app.undoHistory.history.length, 0);
    state.compress();
    state.poll(3);
    assert.equal(app.undoHistory.history.length, 1);
    send("tool", { action: "undo" });
    assert.equal(world.get(id).voxelData, "before");
    send("tool", { action: "redo" });
    assert.equal(world.get(id).voxelData, "compressed-1");
});

test("voxel actions reject locks, foreign avatars and tablet pointers and stop on permission loss", () => {
    const environment = editor();
    const { state, world, selection, Controller, send, frame } = environment;
    const id = volume(environment, { locked: true });
    const click = () => Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
    click();
    world.get(id).locked = false;
    world.get(id).entityHostType = "avatar";
    world.get(id).owningAvatarID = "other";
    click();
    world.get(id).entityHostType = "domain";
    selection.pointingAtTabletLeft = true;
    click();
    assert.equal(state.voxelWrites.length, 0);
    selection.pointingAtTabletLeft = false;
    send("settings", { voxelEditDynamics: "continuous" });
    click();
    assert.equal(state.voxelWrites.length, 1);
    state.domain = false;
    frame(0.25);
    assert.equal(state.voxelWrites.length, 1);
});

test("controller brushes and sphere/cube removal execute actual voxel APIs and retire strokes", () => {
    const environment = editor();
    const { state, Controller, send, ending, timers } = environment;
    volume(environment);
    send("settings", { voxelEditMode: "sphere", voxelPointerMode: "brush", voxelBrushLength: 2,
        voxelSphereSize: 0.6, voxelRemove: true });
    state.controllerValid = true;
    state.route(Controller.Standard.RTClick, true);
    state.route(Controller.Standard.RTClick, false);
    assert.equal(state.voxelWrites[0].kind, "sphere");
    assert.equal(state.voxelWrites[0].args.at(-1), 0);
    send("settings", { voxelEditMode: "cube", voxelRemove: false });
    state.route(Controller.Standard.RTClick, true);
    state.route(Controller.Standard.RTClick, false);
    assert.equal(state.voxelWrites.at(-1).kind, "cube");
    assert.equal(state.voxelWrites.at(-1).args.at(-1), 255);
    ending.emit();
    assert.equal(timers.size, 0);
    assert.equal(state.mappings.size, 0);
});

test("unsettled voxel compression reports an honest failure without manufacturing history", () => {
    const environment = editor();
    const { state, Controller, tablet, app } = environment;
    volume(environment);
    Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
    Controller.mouseReleaseEvent.emit({});
    state.poll(50);
    assert.equal(app.undoHistory.history.length, 0);
    const status = tablet.qmlMessages.filter(message => message.method === "nativeCreate.status").at(-1);
    assert.equal(status.params.error, true);
    assert.match(status.params.text, /did not settle/);
});


test("intermediate compressed data cannot settle a stroke before native readiness", () => {
    const environment = editor();
    const { state, Controller, app, world, send } = environment;
    const id = volume(environment);
    Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
    Controller.mouseReleaseEvent.emit({});
    world.get(id).voxelData = "intermediate";
    state.poll(5);
    assert.equal(app.undoHistory.history.length, 0);
    state.compress();
    state.poll();
    assert.equal(app.undoHistory.history.length, 1);
    world.get(id).locked = true;
    send("tool", { action: "undo" });
    assert.equal(world.get(id).voxelData, "compressed-1");
    world.get(id).locked = false;
    world.get(id).entityHostType = "avatar";
    world.get(id).owningAvatarID = "other";
    send("tool", { action: "undo" });
    assert.equal(world.get(id).voxelData, "compressed-1");
    world.delete(id);
    send("tool", { action: "undo" });
    assert.equal(app.undoHistory.lastExecutedIndex, 0);
});

test("an externally pending volume waits before its initial undo snapshot", () => {
    const environment = editor();
    const { state, Controller, app } = environment;
    const id = volume(environment);
    state.pendingVoxels[id] = "network-pending";
    Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
    assert.equal(state.voxelWrites.length, 0);
    state.compress();
    Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
    Controller.mouseReleaseEvent.emit({});
    state.compress(); state.poll();
    assert.equal(app.undoHistory.history[0].undoArgs.editEntities[0].properties.voxelData, "network-pending");
});

test("deleted volumes and runtimes without readiness never manufacture voxel undo", () => {
    for (const deleted of [true, false]) {
        const environment = editor();
        const { state, Controller, app, world, Entities, tablet } = environment;
        const id = volume(environment);
        if (!deleted) { Entities.isVoxelDataReady = undefined; }
        Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
        Controller.mouseReleaseEvent.emit({});
        if (deleted) { world.delete(id); } else { state.compress(); }
        state.poll(50);
        assert.equal(app.undoHistory.history.length, 0);
        assert.equal(tablet.qmlMessages.filter(message => message.method === "nativeCreate.status").at(-1).params.error, true);
    }
});

test("continuous controller brush pauses over tablet UI and releases all input", () => {
    const environment = editor();
    const { state, Controller, send, selection, frame, ending } = environment;
    volume(environment);
    send("settings", { voxelPointerMode: "brush", voxelEditDynamics: "continuous" });
    state.controllerValid = true;
    state.route(Controller.Standard.RTClick, true);
    assert.equal(state.voxelWrites.length, 1);
    frame(0.25);
    assert.equal(state.voxelWrites.length, 2);
    selection.pointingAtTabletRight = true;
    frame(0.25);
    assert.equal(state.voxelWrites.length, 2);
    ending.emit();
    frame(0.25);
    assert.equal(state.voxelWrites.length, 2);
});


test("completed unchanged voxel data reports no-op and retains no fabricated history", () => {
    const environment = editor();
    const { state, world, Controller, app, tablet } = environment;
    const id = volume(environment);
    Controller.mousePressEvent.emit({ isLeftButton: true, x: 0, y: 0 });
    Controller.mouseReleaseEvent.emit({});
    delete state.pendingVoxels[id];
    state.poll();
    assert.equal(world.get(id).voxelData, "before");
    assert.equal(app.undoHistory.history.length, 0);
    const status = tablet.qmlMessages.filter(message => message.method === "nativeCreate.status").at(-1).params;
    assert.equal(status.error, false);
    assert.match(status.text, /did not change saved data/);
});
