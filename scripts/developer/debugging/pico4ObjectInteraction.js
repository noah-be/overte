//
//  pico4ObjectInteraction.js
//
//  Runtime diagnostics for the Pico 4 object-interaction input path.
//  SPDX-License-Identifier: Apache-2.0
//

/* global Controller, HMD, MyAvatar, Script, Messages, console */

"use strict";

var SUMMARY_INTERVAL_MS = 1000;
var LEFT = 0;
var RIGHT = 1;
var handNames = ["left", "right"];
var standard = Controller.Standard;
var lastSummary = 0;
var previous = [{}, {}];
var MANIPULATION_CHANNEL = "Hifi-Object-Manipulation";
var counters = {
    samples: 0,
    invalidPose: [0, 0],
    trackingTransitions: [0, 0],
    triggerTransitions: [0, 0],
    triggerClickTransitions: [0, 0],
    gripTransitions: [0, 0],
    targetTransitions: [0, 0],
    manipulationEvents: 0
};

function rounded(value) {
    return Math.round(value * 100) / 100;
}

function poseSummary(pose) {
    return {
        valid: pose.valid,
        translation: pose.valid ? {
            x: rounded(pose.translation.x),
            y: rounded(pose.translation.y),
            z: rounded(pose.translation.z)
        } : null
    };
}

function readHand(hand) {
    var isLeft = hand === LEFT;
    var poseInput = isLeft ? standard.LeftHand : standard.RightHand;
    var triggerInput = isLeft ? standard.LT : standard.RT;
    var triggerClickInput = isLeft ? standard.LTClick : standard.RTClick;
    var gripInput = isLeft ? standard.LeftGrip : standard.RightGrip;
    var pose = Controller.getPoseValue(poseInput);
    return {
        pose: poseSummary(pose),
        trigger: Controller.getValue(triggerInput),
        triggerClick: Controller.getValue(triggerClickInput),
        grip: Controller.getValue(gripInput),
        target: null,
        distance: null
    };
}

function changedAcrossThreshold(before, after, threshold) {
    return (before < threshold && after >= threshold) || (before >= threshold && after < threshold);
}

function recordTransitions(hand, state) {
    var old = previous[hand];
    if (!state.pose.valid) {
        counters.invalidPose[hand] += 1;
    }
    if (old.pose !== undefined && old.pose.valid !== state.pose.valid) {
        counters.trackingTransitions[hand] += 1;
        console.info("PICO4_INTERACTION tracking " + handNames[hand] +
            " valid=" + state.pose.valid);
    }
    if (old.trigger !== undefined && changedAcrossThreshold(old.trigger, state.trigger, 0.95)) {
        counters.triggerTransitions[hand] += 1;
        console.info("PICO4_INTERACTION trigger " + handNames[hand] + " value=" + rounded(state.trigger) +
            " click=" + state.triggerClick);
    }
    if (old.triggerClick !== undefined &&
            changedAcrossThreshold(old.triggerClick, state.triggerClick, 0.5)) {
        counters.triggerClickTransitions[hand] += 1;
        console.info("PICO4_INTERACTION triggerClick " + handNames[hand] +
            " value=" + rounded(state.triggerClick));
    }
    if (old.grip !== undefined && changedAcrossThreshold(old.grip, state.grip, 0.15)) {
        counters.gripTransitions[hand] += 1;
        console.info("PICO4_INTERACTION grip " + handNames[hand] + " value=" + rounded(state.grip) +
            " time=" + Date.now());
    }
    if (old.target !== undefined && old.target !== state.target) {
        counters.targetTransitions[hand] += 1;
        console.info("PICO4_INTERACTION target " + handNames[hand] + " entity=" + state.target +
            " distance=" + state.distance);
    }
    previous[hand] = state;
}

function recordManipulation(channel, message, senderID, localOnly) {
    if (channel !== MANIPULATION_CHANNEL || !localOnly) {
        return;
    }
    var payload;
    try {
        payload = JSON.parse(message);
    } catch (error) {
        return;
    }
    if (payload.action !== "grab" && payload.action !== "release") {
        return;
    }
    counters.manipulationEvents += 1;
    console.info("PICO4_INTERACTION manipulation " + JSON.stringify({
        time: Date.now(),
        action: payload.action,
        entity: payload.grabbedEntity,
        joint: payload.joint
    }));
}

function sample() {
    var left = readHand(LEFT);
    var right = readHand(RIGHT);
    var now = Date.now();

    counters.samples += 1;
    recordTransitions(LEFT, left);
    recordTransitions(RIGHT, right);

    if (now - lastSummary >= SUMMARY_INTERVAL_MS) {
        lastSummary = now;
        console.info("PICO4_INTERACTION sample " + JSON.stringify({
            hmdMounted: HMD.mounted,
            controllersAvailable: HMD.isHandControllerAvailable(),
            thumbsticks: {
                lx: rounded(Controller.getValue(standard.LX)),
                ly: rounded(Controller.getValue(standard.LY)),
                rx: rounded(Controller.getValue(standard.RX)),
                ry: rounded(Controller.getValue(standard.RY))
            },
            left: left,
            right: right
        }));
    }
}

Script.update.connect(sample);
Messages.subscribe(MANIPULATION_CHANNEL);
Messages.messageReceived.connect(recordManipulation);

console.info("PICO4_INTERACTION started; exercise near/far grab, trigger, release and both hands.");

Script.scriptEnding.connect(function () {
    Script.update.disconnect(sample);
    Messages.messageReceived.disconnect(recordManipulation);
    Messages.unsubscribe(MANIPULATION_CHANNEL);
    console.info("PICO4_INTERACTION summary " + JSON.stringify(counters));
});
