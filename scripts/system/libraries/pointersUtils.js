"use strict";

//  pointerUtils.js
//
//  Copyright 2017-2018 High Fidelity, Inc.
//  Copyright 2022-2025 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

/* jslint bitwise: true */

/* global Script, Pointers, Settings, console,
   DEFAULT_SEARCH_SPHERE_DISTANCE, COLORS_GRAB_SEARCHING_HALF_SQUEEZE, COLORS_GRAB_SEARCHING_FULL_SQUEEZE,
   COLORS_GRAB_DISTANCE_HOLD, TRIGGER_ON_VALUE, PICO_TRIGGER_OFF_VALUE,
   PICO_LASER_ON_VALUE, PICO_FAR_SELECT_ON_VALUE,
   PICO_INTERACTION_TRACE_MODE,
   Pointer:true, PointerManager:true
*/

Script.include("/~/system/libraries/controllerDispatcherUtils.js");
var Pointer = function(hudLayer, pickType, pointerData) {
    const SEARCH_SPHERE_SIZE = 0.03;
    const SEARCH_LINE_POINTS = 32;
    const SEARCH_LINE_THICKNESS = 0.003;
    const CLICK_LINE_THICKNESS = 0.01;
    const CURSOR_DEFAULT_URL = `${Script.resourcesPath()}images/laser_cursor_default.png`;
    const CURSOR_GRABBING_URL = `${Script.resourcesPath()}images/laser_cursor_grabbing.png`;
    const BEAM_IMAGE_URL = `${Script.resourcesPath()}images/laser_beam_default.png`;
    const DEFAULT_POINTER_RENDER_DISTANCE =
        Settings.getValue("deferTabletCreationUntilOpen", false) ?
            20.0 : DEFAULT_SEARCH_SPHERE_DISTANCE;

    const CURSOR_SIZE = { x: SEARCH_SPHERE_SIZE, y: SEARCH_SPHERE_SIZE, z: SEARCH_SPHERE_SIZE };

    // Disable mipmapping on the cursor so the
    // contrast outline doesn't get blurred away
    const CURSOR_SAMPLER = { filter: "linear" };

    const lineRenderLayer = hudLayer ? "hud" : "front";
    const cursorRenderLayer = hudLayer ? "hud" : "front";

    // TODO: Use Controller.Hardware.OpenXR.{LT,RT}Touch
    // to show the hover laser once #1948 is merged
    this.halfPath = {
        type: "PolyLine",
        color: COLORS_GRAB_SEARCHING_HALF_SQUEEZE,
        visible: true,
        faceCamera: true,
        ignorePickIntersection: true,
        renderLayer: lineRenderLayer,
        linePoints: Array(SEARCH_LINE_POINTS).fill(0),
        strokeWidths: Array(SEARCH_LINE_POINTS).fill(SEARCH_LINE_THICKNESS),
        textures: BEAM_IMAGE_URL,
    };
    this.halfEnd = {
        type: "Image",
        imageURL: CURSOR_DEFAULT_URL,
        emissive: true,
        billboardMode: "full",
        dimensions: CURSOR_SIZE,
        color: COLORS_GRAB_SEARCHING_HALF_SQUEEZE,
        ignorePickIntersection: true,
        renderLayer: cursorRenderLayer,
        sampler: CURSOR_SAMPLER,
        visible: true
    };

    this.fullPath = {
        type: "PolyLine",
        color: COLORS_GRAB_SEARCHING_FULL_SQUEEZE,
        visible: true,
        faceCamera: true,
        ignorePickIntersection: true,
        renderLayer: lineRenderLayer,
        linePoints: Array(SEARCH_LINE_POINTS).fill(0),
        strokeWidths: Array(SEARCH_LINE_POINTS).fill(CLICK_LINE_THICKNESS),
        textures: BEAM_IMAGE_URL,
    };
    this.fullEnd = {
        type: "Image",
        imageURL: CURSOR_DEFAULT_URL,
        emissive: true,
        billboardMode: "full",
        dimensions: CURSOR_SIZE,
        solid: true,
        color: COLORS_GRAB_SEARCHING_FULL_SQUEEZE,
        ignorePickIntersection: true,
        renderLayer: cursorRenderLayer,
        sampler: CURSOR_SAMPLER,
        visible: true
    };

    this.holdPath = {
        type: "PolyLine",
        color: COLORS_GRAB_DISTANCE_HOLD,
        visible: true,
        faceCamera: true,
        ignorePickIntersection: true,
        renderLayer: lineRenderLayer,
        linePoints: Array(SEARCH_LINE_POINTS).fill(0),
        strokeWidths: Array(SEARCH_LINE_POINTS).fill(CLICK_LINE_THICKNESS),
        textures: BEAM_IMAGE_URL,
    };
    this.holdEnd = {
        type: "Image",
        imageURL: CURSOR_GRABBING_URL,
        emissive: true,
        billboardMode: "full",
        dimensions: CURSOR_SIZE,
        solid: true,
        color: COLORS_GRAB_DISTANCE_HOLD,
        alpha: 0.5,
        ignorePickIntersection: true,
        renderLayer: cursorRenderLayer,
        sampler: CURSOR_SAMPLER,
        visible: true
    };

    this.renderStates = [
        {name: "half", path: this.halfPath, end: this.halfEnd},
        {name: "full", path: this.fullPath, end: this.fullEnd},
        {name: "hold", path: this.holdPath, end: this.holdEnd}
    ];

    this.defaultRenderStates = [
        {name: "half", distance: DEFAULT_POINTER_RENDER_DISTANCE, path: this.halfPath},
        {name: "full", distance: DEFAULT_POINTER_RENDER_DISTANCE, path: this.fullPath},
        {name: "hold", distance: DEFAULT_POINTER_RENDER_DISTANCE, path: this.holdPath}
    ];


    this.pointerID = null;
    this.visible = false;
    this.locked = false;
    this.lastRenderState = "";
    this.allwaysOn = false;
    this.hand = pointerData.hand;
    delete pointerData.hand;

    function createPointer(pickType, pointerData) {
        if (pickType == PickType.Ray) {
            var pointerID = Pointers.createRayPointer(pointerData);
            Pointers.setRenderState(pointerID, "");
            Pointers.enablePointer(pointerID);
            return pointerID;
        } else {
            print(`pointerUtils.js createPointer: ray type ${pickType} not supported`);
        }
    }

    this.enable = function() {
        Pointers.enablePointer(this.pointerID);
    };

    this.disable = function() {
        Pointers.disablePointer(this.pointerID);
    };

    this.removePointer = function() {
        Pointers.removePointer(this.pointerID);
    };

    this.makeVisible = function() {
        this.visible = true;
    };

    this.makeInvisible = function() {
        this.visible = false;
    };

    this.lockEnd = function(lockData) {
        if (lockData !== undefined) {
            if (this.visible && !this.locked && lockData.targetID !== null) {
                var targetID = lockData.targetID;
                var targetIsOverlay = lockData.isOverlay;
                if (lockData.offset === undefined) {
                    Pointers.setLockEndUUID(this.pointerID, targetID, targetIsOverlay);
                } else {
                    Pointers.setLockEndUUID(this.pointerID, targetID, targetIsOverlay, lockData.offset);
                }
                this.locked = targetID;
                Pointers.setRenderState(this.pointerID, "hold");
                this.lastRenderState = "hold";
                if (typeof PICO_INTERACTION_TRACE_MODE !== "undefined" &&
                        PICO_INTERACTION_TRACE_MODE !== "off") {
                    console.info("PICO4_LASER " + JSON.stringify({
                        event: "lock", hand: this.hand, target: targetID, time: Date.now()
                    }));
                }
            }
        } else if (this.locked) {
            Pointers.setLockEndUUID(this.pointerID, null, false);
            this.locked = false;
            Pointers.setRenderState(this.pointerID, "");
            this.lastRenderState = "";
            if (typeof PICO_INTERACTION_TRACE_MODE !== "undefined" &&
                    PICO_INTERACTION_TRACE_MODE !== "off") {
                console.info("PICO4_LASER " + JSON.stringify({
                    event: "unlock", hand: this.hand, time: Date.now()
                }));
            }
        }
    };

    this.updateRenderState = function(triggerClicks, triggerValues) {
        var mode = "";
        var picoPointer = Settings.getValue("deferTabletCreationUntilOpen", false);
        if (this.visible) {
            if (this.locked) {
                mode = "hold";
            } else if (picoPointer
                    ? triggerValues[this.hand] >= PICO_FAR_SELECT_ON_VALUE ||
                        (this.lastRenderState === "full" &&
                            triggerValues[this.hand] >= PICO_FAR_SELECT_ON_VALUE - 0.05)
                    : triggerClicks[this.hand]) {
                mode = "full";
            } else if (triggerValues[this.hand] >= (picoPointer
                    ? PICO_LASER_ON_VALUE : TRIGGER_ON_VALUE) ||
                    (picoPointer && this.lastRenderState === "half" &&
                        triggerValues[this.hand] > PICO_TRIGGER_OFF_VALUE) || this.alwaysOn) {
                mode = "half";
            }
        }

        if (picoPointer && mode !== this.lastRenderState &&
                typeof PICO_INTERACTION_TRACE_MODE !== "undefined" &&
                PICO_INTERACTION_TRACE_MODE !== "off") {
            console.info("PICO4_LASER " + JSON.stringify({
                event: "render-state",
                hand: this.hand,
                mode: mode || "hidden",
                reason: this.locked ? "locked" :
                    (mode === "full" ? "select-threshold" :
                        (mode === "half" ? "laser-threshold" : "below-laser-threshold")),
                triggerValue: triggerValues[this.hand],
                triggerClick: !!triggerClicks[this.hand],
                target: this.locked || null,
                time: Date.now()
            }));
        }

        if (mode !== this.lastRenderState) {
            Pointers.setRenderState(this.pointerID, mode);
            this.lastRenderState = mode;
        }
    };

    pointerData.renderStates = this.renderStates;
    pointerData.defaultRenderStates = this.defaultRenderStates;
    this.pointerID = createPointer(pickType, pointerData);
};


var PointerManager = function() {
    this.pointers = [];

    this.createPointer = function(hudLayer, pickType, pointerData) {
        var pointer = new Pointer(hudLayer, pickType, pointerData);
        this.pointers.push(pointer);
        return pointer.pointerID;
    };

    this.makePointerVisible = function(laserParams) {
        var index = laserParams.hand;
        if (index < this.pointers.length && index >= 0) {
            this.pointers[index].makeVisible();
            this.pointers[index].alwaysOn = laserParams.alwaysOn;
        }
    };

    this.makePointerInvisible = function(laserParams) {
        var index = laserParams.hand;
        if (index < this.pointers.length && index >= 0) {
            this.pointers[index].makeInvisible();
        }
    };

    this.forceHandPointerVisible = function(hand) {
        if (hand >= 0 && hand < this.pointers.length) {
            this.pointers[hand].makeVisible();
            this.pointers[hand].alwaysOn = true;
        }
    };

    this.makeTriggerPointerVisible = function(hand) {
        if (hand >= 0 && hand < this.pointers.length) {
            this.pointers[hand].makeVisible();
        }
    };

    this.lockPointerEnd = function(laserParams, lockData) {
        var index = laserParams.hand;
        if (index < this.pointers.length && index >= 0) {
            this.pointers[index].lockEnd(lockData);
        }
    };

    this.updatePointersRenderState = function(triggerClicks, triggerValues) {
        for (var index = 0; index < this.pointers.length; index++) {
            this.pointers[index].updateRenderState(triggerClicks, triggerValues);
        }
    };

    this.removePointers = function() {
        for (var index = 0; index < this.pointers.length; index++) {
            this.pointers[index].removePointer();
        }
        this.pointers = [];
    };
};
