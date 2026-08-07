"use strict";
/* jslint vars: true, plusplus: true */

//
//  defaultScripts.js
//
//  Copyright 2014 High Fidelity, Inc.
//  Copyright 2026 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

// Keep the phone startup set deliberately small. These scripts provide the
// established touch controls and essential client services without loading the
// legacy Android action bar, which depends on a native Home activity that the
// phone client does not provide.
var DEFAULT_SCRIPTS_COMBINED = [
    "system/progress.js",
    "system/+android_interface/touchscreenvirtualpad.js",
    "system/+android_phoneInterface/mobileActionBar.js",
    "system/+android_interface/modes.js",
    "system/makeUserConnection.js"
];

var DEBUG_SCRIPTS = [
    "system/+android_interface/stats.js"
];

var MENU_CATEGORY = "Developer";
var MENU_ITEM = "Debug defaultScripts.js";
var SETTINGS_KEY = "_debugDefaultScriptsIsChecked";
var previousSetting = Settings.getValue(SETTINGS_KEY);

if (previousSetting === "" || previousSetting === false || previousSetting === "false") {
    previousSetting = false;
}

if (previousSetting === true || previousSetting === "true") {
    previousSetting = true;
}

if (Menu.menuExists(MENU_CATEGORY) && !Menu.menuItemExists(MENU_CATEGORY, MENU_ITEM)) {
    Menu.addMenuItem({
        menuName: MENU_CATEGORY,
        menuItemName: MENU_ITEM,
        isCheckable: true,
        isChecked: previousSetting,
        grouping: "Advanced"
    });
}

function includeScripts(scripts) {
    for (var i = 0; i < scripts.length; i++) {
        Script.include(scripts[i]);
    }
}

function loadScripts(scripts) {
    for (var i = 0; i < scripts.length; i++) {
        Script.load(scripts[i]);
    }
}

function runDefaultsTogether() {
    includeScripts(DEFAULT_SCRIPTS_COMBINED);
    if (Script.isDebugMode()) {
        includeScripts(DEBUG_SCRIPTS);
    }
}

function runDefaultsSeparately() {
    loadScripts(DEFAULT_SCRIPTS_COMBINED);
    if (Script.isDebugMode()) {
        loadScripts(DEBUG_SCRIPTS);
    }
}

if (Menu.isOptionChecked(MENU_ITEM)) {
    runDefaultsSeparately();
} else {
    runDefaultsTogether();
}

function menuItemEvent(menuItem) {
    if (menuItem === MENU_ITEM) {
        Settings.setValue(SETTINGS_KEY, Menu.isOptionChecked(MENU_ITEM));
        Menu.triggerOption("Reload All Scripts");
    }
}

function removeMenuItem() {
    if (!Menu.isOptionChecked(MENU_ITEM)) {
        Menu.removeMenuItem(MENU_CATEGORY, MENU_ITEM);
    }
}

Script.scriptEnding.connect(removeMenuItem);
Menu.menuItemEvent.connect(menuItemEvent);

// Match the conservative LOD defaults already proven by the legacy Android
// interface on thermally constrained mobile GPUs.
LODManager.automaticLODAdjust = false;
LODManager.lodAngleDeg = 0.248;
