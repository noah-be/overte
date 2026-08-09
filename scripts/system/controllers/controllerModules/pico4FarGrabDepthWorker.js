// High-frequency local Far Grab depth integration for Pico 4.
// Runs in its own script engine so expensive controllerScripts.js updates do
// not reduce thumbstick depth changes to visible steps.
// SPDX-License-Identifier: Apache-2.0

/* global Controller, Entities, Messages, Pointers, Script, Vec3, console,
   PICO_LASER_ON_VALUE, PICO_FAR_SELECT_ON_VALUE, PICO_FAR_GRAB_ON_VALUE,
   PICO_TRIGGER_OFF_VALUE */

"use strict";

Script.include("/~/system/libraries/controllers.js");
Script.include("/~/system/libraries/controllerDispatcherUtils.js");

var CHANNEL = "Pico4-FarGrab-Depth";
var TRACE_CHANNEL = "Pico4-Interaction-Diagnostics";
var DEPTH_STICK_DEADZONE = 0.2;
var DEPTH_SPEED_MULTIPLIER = 3.0;
var MAXIMUM_DEPTH_SPEED = 2.0;
var MAXIMUM_DEPTH_STEP_SECONDS = 0.05;
var MINIMUM_GRAB_RADIUS = 0.25;
var MAXIMUM_GRAB_RADIUS = 20.0;
var activeGrabs = {};
var heldHands = {};
var worldPointers = {};
var pointerModes = { left: "", right: "" };
var traceEnabled = false;

function handleMessage(channel, message, senderID, localOnly) {
    if (!localOnly) {
        return;
    }
    if (channel === TRACE_CHANNEL) {
        traceEnabled = message === "enable" || message === "edges";
        return;
    }
    if (channel !== CHANNEL) {
        return;
    }
    var command;
    try {
        command = JSON.parse(message);
    } catch (error) {
        return;
    }
    if (command.action === "start" && command.entityID &&
            command.initialLocalPosition && Number.isFinite(command.initialGrabRadius)) {
        activeGrabs[command.hand] = {
            entityID: command.entityID,
            initialLocalPosition: command.initialLocalPosition,
            initialGrabRadius: command.initialGrabRadius,
            radius: command.initialGrabRadius,
            lastTrace: 0
        };
        heldHands[command.hand] = true;
    } else if (command.action === "hold") {
        heldHands[command.hand] = true;
    } else if (command.action === "configurePointers") {
        worldPointers.left = command.left;
        worldPointers.right = command.right;
    } else if (command.action === "stop") {
        delete activeGrabs[command.hand];
        delete heldHands[command.hand];
    }
}

function update(deltaTime) {
    ["left", "right"].forEach(function (hand) {
        var pointerID = worldPointers[hand];
        if (pointerID === undefined || pointerID === null) {
            return;
        }
        var trigger = Controller.getValue(hand === "left" ?
            Controller.Standard.LT : Controller.Standard.RT);
        var mode = "";
        // Use the same central threshold as the grab dispatcher.  Waiting only
        // for its later "hold" message made the green state include entity
        // lookup and grab setup time, even though the physical trigger had
        // already crossed the grab threshold.
        if (heldHands[hand] || trigger >= PICO_FAR_GRAB_ON_VALUE) {
            mode = "hold";
        } else if (trigger >= PICO_FAR_SELECT_ON_VALUE) {
            mode = "full";
        } else if (trigger >= PICO_LASER_ON_VALUE ||
                pointerModes[hand] === "half" && trigger > PICO_TRIGGER_OFF_VALUE) {
            mode = "half";
        }
        if (mode !== pointerModes[hand]) {
            if (mode) {
                Pointers.enablePointer(pointerID);
            }
            Pointers.setRenderState(pointerID, mode);
            pointerModes[hand] = mode;
            if (traceEnabled) {
                console.info("PICO4_LASER " + JSON.stringify({
                    event: "worker-render-state", hand: hand, mode: mode || "hidden",
                    triggerValue: trigger, time: Date.now()
                }));
            }
        }
    });

    var depthInput = -Controller.getValue(Controller.Standard.RY);
    if (Math.abs(depthInput) <= DEPTH_STICK_DEADZONE) {
        return;
    }
    var depthDirection = (depthInput > 0 ? 1 : -1) *
        (Math.abs(depthInput) - DEPTH_STICK_DEADZONE) / (1 - DEPTH_STICK_DEADZONE);
    Object.keys(activeGrabs).forEach(function (hand) {
        var grab = activeGrabs[hand];
        var depthSpeed = DEPTH_SPEED_MULTIPLIER *
            Math.min(MAXIMUM_DEPTH_SPEED, Math.max(0.5, grab.radius * 0.8));
        grab.radius += depthDirection * depthSpeed *
            Math.min(deltaTime, MAXIMUM_DEPTH_STEP_SECONDS);
        grab.radius = Math.max(MINIMUM_GRAB_RADIUS, Math.min(MAXIMUM_GRAB_RADIUS, grab.radius));
        var localPosition = Vec3.sum(grab.initialLocalPosition,
            { x: 0, y: grab.radius - grab.initialGrabRadius, z: 0 });
        var updated = Entities.setLocalEntityPosition(grab.entityID, localPosition);
        var now = Date.now();
        if (traceEnabled && now - grab.lastTrace >= 100) {
            grab.lastTrace = now;
            console.info("PICO4_FAR_DEPTH " + JSON.stringify({
                source: "worker", hand: hand, input: depthInput,
                frameSeconds: deltaTime, radius: grab.radius,
                localPosition: localPosition, nativeUpdated: updated, time: now
            }));
        }
    });
}

Messages.subscribe(CHANNEL);
Messages.subscribe(TRACE_CHANNEL);
Messages.messageReceived.connect(handleMessage);
Script.update.connect(update);

function announceReady() {
    Messages.sendLocalMessage(CHANNEL, JSON.stringify({ action: "ready" }));
}
announceReady();
Script.setTimeout(announceReady, 250);
Script.setTimeout(announceReady, 1000);

Script.scriptEnding.connect(function () {
    Script.update.disconnect(update);
    Messages.messageReceived.disconnect(handleMessage);
    Messages.unsubscribe(CHANNEL);
    Messages.unsubscribe(TRACE_CHANNEL);
});
