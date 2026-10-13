"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const path = require("node:path");
const { createBridge, properties } = require("../../../scripts/system/create/modules/nativeCreateBridge.js");
const { runProductionScript, createTabletApi } = require("../support");

function start() {
    const world = new Map([
        ["shape", { type: "Shape", name: "Example", position: { x: 1, y: 2, z: 3 },
            entityHostType: "domain", locked: false, visible: true, script: "", serverScripts: "" }],
        ["mine", { type: "Model", name: "Mine", position: { x: 1, y: 2, z: 3 },
            entityHostType: "avatar", owningAvatarID: "self", locked: false, script: "", serverScripts: "", modelURL: "" }],
        ["foreign", { type: "Model", name: "Foreign", position: { x: 1, y: 2, z: 3 },
            entityHostType: "avatar", owningAvatarID: "other", locked: false, script: "", serverScripts: "", modelURL: "" }]
    ]);
    const state = { active: true, domain: true, avatar: true, locks: false, numeric: false,
        edits: [], commands: [], imports: [], created: [], messages: [], cancelled: 0 };
    const selection = { selections: [], setSelections(ids) { this.selections = ids; },
        duplicateSelection() { state.commands.push("duplicate"); },
        copySelectedEntities() { state.commands.push("copy"); },
        pasteEntities() { state.commands.push("paste"); },
        moveEntitiesSelectionToAvatar() { state.commands.push("move"); }, addEventListener() {} };
    const entities = {
        getEntityProperties: id => structuredClone(world.get(id) || {}),
        findEntities: () => [...world.keys()],
        getMultipleEntityProperties: ids => ids.map(id => entities.getEntityProperties(id)),
        canRez: () => state.domain, canRezTmp: () => false,
        canRezAvatarEntities: () => state.avatar, canAdjustLocks: () => state.locks,
        editEntity(id, patch) { state.edits.push([id, patch]); Object.assign(world.get(id), patch); }
    };
    const Tablet = createTabletApi();
    function CreateWindow() {
        this.webEventReceived = { addListener() {} };
        this.interactiveWindowHidden = { addListener() {} };
        this.setVisible = () => {};
        this.isVisible = () => false;
    }
    const listScript = path.resolve(__dirname, "../../../scripts/system/create/entityList/entityList.js");
    const { context: listContext } = runProductionScript(listScript, {
        Script: { require: () => CreateWindow, resolvePath: value => value },
        Window: {}, Tablet, Entities: entities, HMD: { active: false },
        MyAvatar: { position: { x: 0, y: 0, z: 0 }, sessionUUID: "self", SELF_ID: "self" },
        SelectionDisplay: { getSpaceMode: () => "world" },
        Camera: { position: { x: 0, y: 0, z: 0 } },
        Vec3: { distance: () => 1 }, print() {}, console
    });
    const list = new listContext.EntityListTool(() => true, selection);
    list.createApp = { getParentState: () => "NONE" };
    const context = {
        entities, avatar: { sessionUUID: "self", SELF_ID: "self" }, selection,
        history: { canUndo: () => true, canRedo: () => false,
            undo: () => state.commands.push("undo"), redo: () => state.commands.push("redo") },
        app: { deleteSelectedEntities() { selection.selections.forEach(id => world.delete(id)); state.commands.push("delete"); },
            parentSelectedEntities() {}, unparentSelectedEntities() {}, setCameraFocusToSelection() {},
            alignGridToAvatar() {}, alignGridToSelection() {}, toggleGridVisibility() { state.commands.push("grid"); } },
        grid: { getSnapToGrid: () => false, setSnapToGrid: () => state.commands.push("snap") },
        display: { toggleSpaceMode() {}, rotate90degreeSelection() {} },
        isActive: () => state.active,
        send: message => state.messages.push(message), euler: value => value,
        refresh: () => list.sendUpdate(),
        applyProperties: (id, patch, preview) => { entities.editEntity(id, patch); state.commands.push(preview ? "preview" : "edit"); },
        create: (patch, host) => { state.created.push([patch, host]); return "created"; },
        numericFocus: value => { state.numeric = value; }, isNumericEditing: () => state.numeric,
        importEntities: options => { state.imports.push(options); return state.importResult || { ok: true, ids: ["imported"] }; },
        browse: callback => { state.browse = callback; }, cancelBrowse: () => state.cancelled++,
        exportSelection: () => state.commands.push("export"), showAssets: () => state.commands.push("assets")
    };
    const bridge = createBridge(context);
    list.onNativeEvent = bridge.acceptList;
    const send = (method, params = {}) => bridge.handle({ method: "nativeCreate." + method, params });
    const status = () => state.messages.filter(message => message.method === "nativeCreate.status").at(-1)?.params;
    return { state, world, selection, bridge, send, status };
}

test("native Create reuses the production entity scan and excludes foreign avatar entities", () => {
    const { state, selection, send } = start();
    send("ready");
    const list = state.messages.find(message => message.method === "nativeCreate.list");
    assert.deepEqual(Array.from(list.params.entities, item => item.id), ["shape", "mine"]);
    send("select", { ids: ["shape"] });
    assert.deepEqual(selection.selections, ["shape"]);
    send("select", { ids: ["foreign"] });
    assert.deepEqual(selection.selections, ["shape"]);
});

test("native property messages reject stale, locked, unowned and malformed edits", () => {
    const { state, world, selection, send } = start();
    selection.selections = ["shape"];
    send("edit", { id: "other", properties: { name: "wrong" } });
    world.get("shape").locked = true;
    send("edit", { id: "shape", properties: { name: "locked" } });
    selection.selections = ["foreign"];
    send("edit", { id: "foreign", properties: { name: "unowned" } });
    selection.selections = ["mine"];
    send("edit", { id: "mine", properties: { owningAvatarID: "attacker" } });
    send("edit", { id: "mine", properties: { position: { x: NaN, y: 0, z: 0 } } });
    assert.equal(state.edits.length, 0);
    send("edit", { id: "mine", properties: { name: "Renamed", modelURL: "https://example.test/avatar.glb" } });
    assert.equal(world.get("mine").name, "Renamed");
    assert.equal(state.edits.length, 1);
    state.avatar = false;
    send("edit", { id: "mine", properties: { name: "revoked" } });
    assert.equal(world.get("mine").name, "Renamed");
});

test("lock changes require lock permission and only unlocking is allowed on a locked selection", () => {
    const { state, world, selection, send } = start();
    selection.selections = ["shape"];
    world.get("shape").locked = true;
    send("edit", { id: "shape", properties: { locked: false } });
    assert.equal(state.edits.length, 0);
    state.locks = true;
    send("edit", { id: "shape", properties: { locked: false, name: "also mutate" } });
    assert.equal(state.edits.length, 0);
    send("edit", { id: "shape", properties: { locked: false } });
    assert.equal(world.get("shape").locked, false);
});

test("native preview preserves the numeric transaction and tools delegate to existing operations", () => {
    const { state, world, selection, send } = start();
    selection.selections = ["shape"];
    send("preview", { id: "shape", properties: { position: { x: 4, y: 5, z: 6 } } });
    assert.equal(state.edits.length, 0);
    send("numericFocus", { focused: true });
    send("preview", { id: "shape", properties: { position: { x: 4, y: 5, z: 6 } } });
    assert.equal(world.get("shape").position.x, 4);
    send("tool", { action: "grid-visible" });
    assert.equal(state.numeric, false);
    send("tool", { action: "duplicate" });
    send("tool", { action: "undo" });
    send("tool", { action: "redo" });
    assert.deepEqual(state.commands, ["preview", "grid", "duplicate", "undo", "redo"]);
    send("tool", { action: "delete" });
    assert.equal(world.has("shape"), false);
    state.active = false;
    send("tool", { action: "paste" });
    assert.equal(state.commands.includes("paste"), false);
});

test("native imports validate URLs, permissions and placement and retire pending file results", () => {
    const { state, bridge, send, status } = start();
    send("import", { url: "javascript:alert(1)" });
    send("import", { url: "https://secret@example.test/entities.json" });
    send("import", { url: "https://example.test/entities.json", position: { x: Infinity, y: 0, z: 0 } });
    assert.equal(state.imports.length, 0);
    state.domain = false;
    send("import", { url: "https://example.test/entities.json" });
    assert.equal(state.imports.length, 0);
    send("import", { url: "https://example.test/entities.json", host: "avatar", position: { x: 1, y: 2, z: 3 } });
    assert.equal(state.imports[0].host, "avatar");
    assert.equal(status().error, false);
    state.importResult = { ok: false, error: "Import failed", ids: [] };
    send("import", { url: "atp:/entities.json", host: "avatar" });
    assert.equal(status().text, "Import failed");
    send("browse", { host: "avatar" });
    const stale = state.browse;
    bridge.reset();
    stale("/private/selected-file.json");
    assert.equal(state.imports.length, 2);
    assert.equal(state.cancelled, 1);
});

test("native creation and property schemas preserve immutable identity and bounded JSON", () => {
    const { state, send } = start();
    send("create", { properties: { type: "Model", modelURL: "https://example.test/model.glb" }, host: "avatar" });
    assert.equal(state.created.length, 1);
    send("create", { properties: { type: "Unknown" } });
    send("create", { properties: { type: "Shape", entityHostType: "avatar" } });
    assert.equal(state.created.length, 1);
    assert.equal(properties(JSON.parse('{"__proto__":{"polluted":true}}'), false), null);
    assert.equal(properties({ dimensions: { x: 0, y: 1, z: 1 } }, false), null);
});
