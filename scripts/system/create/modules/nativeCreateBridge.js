// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
"use strict";

// Native tablet transport for the existing Create editor. World operations,
// selection, property conversion, undo and imports remain owned by edit.js.
var READ_ONLY = ["id", "type", "entityHostType", "avatarEntity", "owningAvatarID",
    "created", "lastEdited", "lastEditedBy", "age", "ageAsText", "boundingBox",
    "naturalDimensions", "renderInfo", "queryAACube", "children"];
var TYPES = ["Shape", "Model", "Light", "Text", "Image", "Web", "Zone",
    "ParticleEffect", "ProceduralParticleEffect", "Material", "PolyVox", "Grid",
    "Sound", "Canvas", "Empty", "Script"];

function record(value) {
    return value && typeof value === "object" && !Array.isArray(value);
}

function finite(value) { return typeof value === "number" && isFinite(value); }

function vector(value) {
    return record(value) && finite(value.x) && finite(value.y) && finite(value.z);
}

function jsonValue(value, depth) {
    if (depth > 8) { return false; }
    if (value === null || typeof value === "boolean" || typeof value === "string") {
        return typeof value !== "string" || value.length <= 131072;
    }
    if (typeof value === "number") { return finite(value); }
    if (Array.isArray(value)) {
        return value.length <= 1024 && value.every(function (item) { return jsonValue(item, depth + 1); });
    }
    if (!record(value)) { return false; }
    return Object.keys(value).length <= 256 && Object.keys(value).every(function (key) {
        return key !== "__proto__" && key !== "prototype" && key !== "constructor"
            && jsonValue(value[key], depth + 1);
    });
}

function properties(value, creating) {
    if (!record(value) || Object.keys(value).length === 0 || !jsonValue(value, 0)) { return null; }
    if (Object.keys(value).some(function (key) {
        return READ_ONLY.indexOf(key) !== -1 && !(creating && key === "type");
    })) { return null; }
    if (JSON.stringify(value).length > 131072) { return null; }
    for (var i = 0; i < 3; i++) {
        var name = ["position", "rotation", "dimensions"][i];
        if (value[name] !== undefined && !vector(value[name])) { return null; }
    }
    if (value.dimensions && (value.dimensions.x <= 0 || value.dimensions.y <= 0 || value.dimensions.z <= 0)) {
        return null;
    }
    for (var j = 0; j < 4; j++) {
        var flag = ["visible", "dynamic", "collisionless", "locked"][j];
        if (value[flag] !== undefined && typeof value[flag] !== "boolean") { return null; }
    }
    return JSON.parse(JSON.stringify(value));
}

function editableProperties(value) {
    var result = {};
    Object.keys(value || {}).forEach(function (key) {
        if (key !== "locked" && READ_ONLY.indexOf(key) === -1 && jsonValue(value[key], 0)) { result[key] = value[key]; }
    });
    return result;
}

function createBridge(context) {
    var knownIDs = Object.create(null);
    var browseGeneration = 0;
    var browsing = false;

    function send(kind, params) { context.send({ method: "nativeCreate." + kind, params: params }); }
    function status(text, error) { send("status", { text: text, error: error === true }); }
    function hostAllowed(host) {
        return host === "avatar" ? context.entities.canRezAvatarEntities()
            : host === "domain" && (context.entities.canRez() || context.entities.canRezTmp());
    }
    function owned(value) {
        return !(value.avatarEntity || value.entityHostType === "avatar")
            || value.owningAvatarID === context.avatar.sessionUUID || value.owningAvatarID === context.avatar.SELF_ID;
    }
    function canEdit(id, unlocking) {
        var value = context.entities.getEntityProperties(id);
        if (!value || !value.type || !owned(value)) { return false; }
        if (value.locked && !unlocking) { return false; }
        if (unlocking && !context.entities.canAdjustLocks()) { return false; }
        return value.entityHostType === "local" || hostAllowed(value.entityHostType || "domain");
    }
    function selectedIDs() { return context.selection.selections.map(function (id) { return id.toString(); }); }

    function selection() {
        if (!context.isActive()) { return; }
        var ids = selectedIDs();
        var values = ids.map(function (id) {
            var value = context.entities.getEntityProperties(id);
            if (context.propertyView) { value = context.propertyView(value); }
            else {
                if (value.rotation) { value.rotation = context.euler(value.rotation); }
                if (value.localRotation) { value.localRotation = context.euler(value.localRotation); }
            }
            return { id: id, type: value.type, editable: canEdit(id, false),
                properties: editableProperties(value), locked: value.locked === true,
                canLock: !value.locked && canEdit(id, false) && context.entities.canAdjustLocks(),
                canUnlock: value.locked === true && canEdit(id, true) };
        });
        send("selection", { entities: values,
            canUndo: context.history.canUndo() && (!context.canReplayHistory || context.canReplayHistory("undo")),
            canRedo: context.history.canRedo() && (!context.canReplayHistory || context.canReplayHistory("redo")) });
    }
    function acceptList(data) {
        if (!context.isActive()) { return; }
        if (data.type === "update" && Array.isArray(data.entities)) {
            knownIDs = Object.create(null);
            data.entities.forEach(function (value) { knownIDs[value.id.toString()] = true; });
            send("list", { entities: data.entities, selectedIDs: selectedIDs() });
        } else if (data.type === "clearEntityList") {
            knownIDs = Object.create(null);
            send("list", { entities: [], selectedIDs: [] });
        }
    }
    function sendSettings(settings) {
        if (context.isActive()) { send("settings", settings); }
    }
    function applySettings(params) {
        var enums = { createAppMode: ["object", "voxel"], voxelEditMode: ["single", "sphere", "cube"],
            voxelEditDynamics: ["click", "continuous"], voxelPointerMode: ["laser", "brush"] };
        var keys = Object.keys(params);
        if (!keys.length || keys.some(function(key) {
            if (Object.prototype.hasOwnProperty.call(enums, key)) { return enums[key].indexOf(params[key]) === -1; }
            if (key === "voxelRemove") { return typeof params[key] !== "boolean"; }
            if (key === "voxelSphereSize") { return !finite(params[key]) || params[key] <= 0 || params[key] > 100; }
            if (key === "voxelBrushLength") { return !finite(params[key]) || params[key] < 0 || params[key] > 100; }
            return true;
        })) { status("Invalid voxel tool settings.", true); return; }
        if (!hostAllowed("domain") && !hostAllowed("avatar") && params.createAppMode !== "object") {
            status("You do not have voxel editing permission.", true); return;
        }
        context.numericFocus(false);
        context.applyEditSettings(params);
        status(params.createAppMode === "object" ? "Object editing enabled." : "Voxel settings applied.");
    }

    function importEntities(params, trustedFile) {
        var url = params.url;
        var host = params.host || "domain";
        if (typeof url !== "string" || !url.trim() || url.length > 8192 || /[\r\n]/.test(url)
                || (!trustedFile && !/^(https?:\/\/|atp:)/i.test(url))
                || /^https?:\/\/[^/]*@/i.test(url)) {
            status("Enter an HTTP, HTTPS or ATP entity JSON URL, or choose a local file.", true);
            return;
        }
        if (!hostAllowed(host)) { status("You do not have permission to import to this entity host.", true); return; }
        if (params.position !== undefined && !vector(params.position)) { status("Import position must contain finite numbers.", true); return; }
        status("Importing entities…");
        var outcome = context.importEntities({ url: url.trim(), host: host, position: params.position });
        status(outcome && outcome.ok ? "Imported " + outcome.ids.length + " entities."
            : (outcome && outcome.error || "Entity import failed."), !outcome || !outcome.ok);
        context.refresh();
        selection();
    }

    var tools = {
        delete: function () { context.app.deleteSelectedEntities(); },
        duplicate: function () { context.selection.duplicateSelection(); },
        copy: function () { context.selection.copySelectedEntities(); },
        paste: function () { context.selection.pasteEntities(); },
        undo: function () { context.history.undo(); },
        redo: function () { context.history.redo(); },
        parent: function () { context.app.parentSelectedEntities(); },
        unparent: function () { context.app.unparentSelectedEntities(); },
        focus: function () { context.app.setCameraFocusToSelection(); },
        "move-to-avatar": function () { context.selection.moveEntitiesSelectionToAvatar(); },
        "grid-avatar": function () { context.app.alignGridToAvatar(); },
        "grid-selection": function () { context.app.alignGridToSelection(); },
        "grid-visible": function () { context.app.toggleGridVisibility(); },
        "grid-snap": function () { context.grid.setSnapToGrid(!context.grid.getSnapToGrid()); },
        "space-mode": function () { context.display.toggleSpaceMode(); },
        "rotate-x": function () { context.display.rotate90degreeSelection("X"); },
        "rotate-y": function () { context.display.rotate90degreeSelection("Y"); },
        "rotate-z": function () { context.display.rotate90degreeSelection("Z"); },
        export: function () { context.exportSelection(); },
        assets: function () { context.showAssets(); }
    };
    var noSelection = ["paste", "undo", "redo", "grid-avatar", "grid-visible", "grid-snap", "space-mode", "assets"];
    var readSelection = ["copy", "focus", "export", "grid-selection"];

    function handle(message) {
        if (!record(message) || typeof message.method !== "string" || message.method.indexOf("nativeCreate.") !== 0) {
            return false;
        }
        if (!context.isActive()) { return true; }
        var params = message.params || {};
        if (!record(params)) { status("Invalid editor request.", true); return true; }
        var method = message.method.slice("nativeCreate.".length);
        var ids = selectedIDs();
        var patch;
        if (method === "ready" || method === "refresh") {
            context.refresh();
            selection();
            if (context.editSettings) { sendSettings(context.editSettings()); }
        } else if (method === "select") {
            if (!Array.isArray(params.ids) || params.ids.length > 256 || params.ids.some(function (id) {
                return typeof id !== "string" || !knownIDs[id];
            })) { status("Refresh the list before selecting these entities.", true); return true; }
            context.selection.setSelections(params.ids, bridge);
            selection();
        } else if (method === "edit" || method === "preview") {
            var unlocking = record(params.properties) && Object.keys(params.properties).length === 1
                && params.properties.locked === false;
            if (ids.length !== 1 || params.id !== ids[0] || !canEdit(ids[0], unlocking)) {
                status("The selection is stale, locked, or you do not own this entity.", true);
                return true;
            }
            patch = properties(params.properties, false);
            if (!patch || (patch.locked !== undefined && !context.entities.canAdjustLocks())) {
                status("Invalid entity properties or lock permission.", true); return true;
            }
            if (method === "preview" && !context.isNumericEditing()) { return true; }
            context.applyProperties(ids[0], patch, method === "preview");
            if (method === "edit") { status("Properties applied."); context.refresh(); }
            selection();
        } else if (method === "numericFocus") {
            if (typeof params.focused !== "boolean") { return true; }
            context.numericFocus(params.focused && ids.length === 1 && canEdit(ids[0], false));
        } else if (method === "create") {
            patch = properties(params.properties, true);
            var host = params.host || "domain";
            if (!patch || TYPES.indexOf(patch.type) === -1 || !hostAllowed(host)
                    || (patch.locked === true && !context.entities.canAdjustLocks())) {
                status("Invalid entity type, properties or creation permission.", true); return true;
            }
            var entityID = context.create(patch, host);
            status(entityID ? "Entity created." : "Entity creation failed.", !entityID);
            selection();
        } else if (method === "tool") {
            if (typeof params.action !== "string" || !Object.prototype.hasOwnProperty.call(tools, params.action)) {
                status("Unknown editor tool.", true); return true;
            }
            if (noSelection.indexOf(params.action) === -1 && ids.length === 0) {
                status("Select an entity first.", true); return true;
            }
            if (readSelection.indexOf(params.action) === -1 && noSelection.indexOf(params.action) === -1
                    && ids.some(function (id) { return !canEdit(id, false); })) {
                status("The selection contains locked or unowned entities.", true); return true;
            }
            if (["paste", "undo", "redo"].indexOf(params.action) !== -1
                    && !hostAllowed("domain") && !hostAllowed("avatar")) {
                status("You no longer have entity editing permission.", true); return true;
            }
            if (["undo", "redo"].indexOf(params.action) !== -1 && context.canReplayHistory
                    && !context.canReplayHistory(params.action)) {
                status("This history operation is unavailable or its entity host permission changed.", true); return true;
            }
            context.numericFocus(false);
            tools[params.action]();
            context.refresh();
            selection();
        } else if (method === "settings") {
            if (context.applyEditSettings) { applySettings(params); }
        } else if (method === "import") {
            importEntities(params, false);
        } else if (method === "browse") {
            if (browsing) { return true; }
            browsing = true;
            var generation = ++browseGeneration;
            context.browse(function (file) {
                if (generation !== browseGeneration) { return; }
                browsing = false;
                if (!context.isActive()) { return; }
                if (typeof file !== "string" || !file) { status("Import cancelled."); return; }
                importEntities({ url: file, host: params.host || "domain", position: params.position }, true);
            });
        } else {
            status("Unknown editor request.", true);
        }
        return true;
    }

    function reset() {
        knownIDs = Object.create(null);
        browseGeneration++;
        browsing = false;
        context.cancelBrowse();
    }
    var bridge = { handle: handle, selection: selection, acceptList: acceptList, reset: reset,
        sendSettings: sendSettings, reportStatus: status };
    return bridge;
}

module.exports = { createBridge: createBridge, properties: properties, editableProperties: editableProperties };
