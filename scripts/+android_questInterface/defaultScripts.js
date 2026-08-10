"use strict";
/* jslint vars: true, plusplus: true */

//
//  defaultScripts.js
//  examples
//
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

// Standalone headsets are more comfortable with the tablet beyond arm's
// immediate near field. WebTablet reads this whenever it is spawned.
Settings.setValue("hmdTabletForwardOffset", 0.95);
Settings.setValue("hmdTabletUpOffset", -0.22);
Settings.setValue("hmdTabletBackwardTiltDegrees", -8);
Settings.setValue("hmdTabletScale", 125);
// Hide only the locally rendered mesh.  The avatar object, skeleton,
// collision, controller joints and network representation remain active.
MyAvatar.shouldRenderLocally = false;
// A single per-hand ray can pick both tablet/world entities and the HUD on
// standalone VR. The desktop dispatcher historically creates separate rays
// for both layers, doubling controller pick work every application update.
Settings.setValue("combineHudAndWorldPointers", true);
// On Pico, constructing the hidden tablet and stylus as a cache warm-up causes
// visible startup flashes and expensive EntityTree work. Create it only when
// it is actually opened.
Settings.setValue("deferTabletCreationUntilOpen", true);

// Keep the Pico movement default migration versioned so experimental defaults
// can be corrected once without continually overriding a speed the user chose.
var PICO_WALK_SPEED_MIGRATION_KEY = "picoVrWalkSpeedDefaultVersion";
var PICO_WALK_SPEED_MIGRATION_VERSION = 2;
var LEGACY_VR_WALK_SPEED = 4.0;
var PREVIOUS_PICO_DEFAULT_VR_WALK_SPEED = 5.0;
var PICO_DEFAULT_VR_WALK_SPEED = 4.0;
var walkSpeedMigrationVersion = Number(Settings.getValue(PICO_WALK_SPEED_MIGRATION_KEY, 0));
if (walkSpeedMigrationVersion < PICO_WALK_SPEED_MIGRATION_VERSION) {
    if (Math.abs(MyAvatar.vrWalkSpeed - LEGACY_VR_WALK_SPEED) < 0.001
            || Math.abs(MyAvatar.vrWalkSpeed - PREVIOUS_PICO_DEFAULT_VR_WALK_SPEED) < 0.001) {
        MyAvatar.vrWalkSpeed = PICO_DEFAULT_VR_WALK_SPEED;
        Settings.setValue("Avatar/vrWalkSpeed", PICO_DEFAULT_VR_WALK_SPEED);
        print("PICO_MOVEMENT restored VR walk speed default to "
            + PICO_DEFAULT_VR_WALK_SPEED + " m/s");
    }
    Settings.setValue(PICO_WALK_SPEED_MIGRATION_KEY, PICO_WALK_SPEED_MIGRATION_VERSION);
}

var DEFAULT_SCRIPTS_COMBINED = [
    // Bring up the core VR UI before any optional service script can block on
    // network or account initialization on a standalone headset.
    "system/tablet-ui/tabletUI.js",
    "system/request-service.js",
    "system/progress.js",
    "system/away.js",
    //"system/hmd.js",
    "system/menu.js",
    "system/bubble.js",
    "system/pal.js", // "system/mod.js", // older UX, if you prefer
    "system/avatarapp.js",
    "system/settings/settings.js",
    "system/makeUserConnection.js",
    // Use Overte's current federated domain directory instead of the legacy
    // user-stories based OLD GOTO application.
    "system/places/places.js",
    "system/notifications.js",
    "system/dialTone.js",
    "system/quickGoto.js",
    "system/tablet-position/tabletPosition.js",
    "system/firstPersonHMD.js"
];
var DEFAULT_SCRIPTS_SEPARATE = [
    // The Create app is bundled locally. Keep its large editor script in its
    // own engine so initialization cannot stall the core tablet/UI scripts.
    "system/create/edit.js",
    "system/controllers/controllerScripts.js",
    //"system/chat.js"
];

if (Window.interstitialModeEnabled && !Window.nativeLoadingScreenEnabled) {
    // Insert interstitial scripts at front so that they're started first.
    DEFAULT_SCRIPTS_COMBINED.splice(0, 0, "system/interstitialPage.js", "system/redirectOverlays.js");
}

// add a menu item for debugging
var MENU_CATEGORY = "Developer > Scripting";
var MENU_ITEM = "Debug defaultScripts.js";

var SETTINGS_KEY = '_debugDefaultScriptsIsChecked';
var previousSetting = Settings.getValue(SETTINGS_KEY);

if (previousSetting === '' || previousSetting === false || previousSetting === 'false') {
    previousSetting = false;
}

if (previousSetting === true || previousSetting === 'true') {
    previousSetting = true;
}

if (Menu.menuExists(MENU_CATEGORY) && !Menu.menuItemExists(MENU_CATEGORY, MENU_ITEM)) {
    Menu.addMenuItem({
        menuName: MENU_CATEGORY,
        menuItemName: MENU_ITEM,
        isCheckable: true,
        isChecked: previousSetting,
    });
}

function loadSeparateDefaults() {
    for (var i in DEFAULT_SCRIPTS_SEPARATE) {
        Script.load(DEFAULT_SCRIPTS_SEPARATE[i]);
    }
}

function runDefaultsTogether() {
    for (var i in DEFAULT_SCRIPTS_COMBINED) {
        Script.include(DEFAULT_SCRIPTS_COMBINED[i]);
    }
    loadSeparateDefaults();
}

function runDefaultsSeparately() {
    for (var i in DEFAULT_SCRIPTS_COMBINED) {
        Script.load(DEFAULT_SCRIPTS_COMBINED[i]);
    }
    loadSeparateDefaults();
}

// start all scripts
if (Menu.isOptionChecked(MENU_ITEM)) {
    // we're debugging individual default scripts
    // so we load each into its own ScriptEngine instance
    runDefaultsSeparately();
} else {
    // include all default scripts into this ScriptEngine
    runDefaultsTogether();
}

function menuItemEvent(menuItem) {
    if (menuItem === MENU_ITEM) {
        var isChecked = Menu.isOptionChecked(MENU_ITEM);
        if (isChecked === true) {
            Settings.setValue(SETTINGS_KEY, true);
        } else if (isChecked === false) {
            Settings.setValue(SETTINGS_KEY, false);
        }
        Menu.triggerOption("Reload All Scripts");
    }
}

function removeMenuItem() {
    if (!Menu.isOptionChecked(MENU_ITEM)) {
        Menu.removeMenuItem(MENU_CATEGORY, MENU_ITEM);
    }
}

Script.scriptEnding.connect(function() {
    removeMenuItem();
});

Menu.menuItemEvent.connect(menuItemEvent);
