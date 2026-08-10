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
var ANDROID_PHONE_INTERFACE = true;
var PHONE_DEFAULT_SCRIPTS = [
    "system/request-service.js",
    "system/progress.js",
    "system/+android_interface/touchscreenvirtualpad.js",
    "system/+android_phoneInterface/mobileActionBar.js",
    "system/+android_phoneInterface/mobileTabletApps.js",
    "system/+android_phoneInterface/phoneEmote.js",
    "system/bubble.js",
    "system/pal.js",
    "system/avatarapp.js",
    "system/places/places.js",
    "system/quickGoto.js"
];

Script.require("/~/system/+android_interface/androidControls.js");

function startPhoneDefaults() {
    for (var i = 0; i < PHONE_DEFAULT_SCRIPTS.length; i++) {
        Script.include(PHONE_DEFAULT_SCRIPTS[i]);
    }
}

startPhoneDefaults();

// Match the conservative LOD defaults already proven by the legacy Android
// interface on thermally constrained mobile GPUs.
LODManager.automaticLODAdjust = false;
LODManager.lodAngleDeg = 0.248;
