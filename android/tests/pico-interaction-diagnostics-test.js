// Device-free behavior test for pico4ObjectInteraction.js.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const dispatcherSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/controllers/controllerDispatcher.js"), "utf8");
const farGrabSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/controllers/controllerModules/farGrabEntity.js"), "utf8");
const farDepthWorkerSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/controllers/controllerModules/pico4FarGrabDepthWorker.js"), "utf8");
const nearGrabSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/controllers/controllerModules/nearGrabEntity.js"), "utf8");
const nearParentSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/controllers/controllerModules/nearParentGrabOverlay.js"), "utf8");
const stationSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/developer/debugging/pico4InteractionTestStation.js"), "utf8");
const dispatcherUtilsSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/libraries/controllerDispatcherUtils.js"), "utf8");
const pointersSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/libraries/pointersUtils.js"), "utf8");
const picoInteractionSettingsSource = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/settings/qml/pages/PicoInteractionSettings.qml"), "utf8");
const applicationSource = fs.readFileSync(path.resolve(__dirname,
    "../../interface/src/Application.cpp"), "utf8");
assert.ok(dispatcherSource.includes(
    "_this.activitySlots.hasOwnProperty(activitySlot)"),
"dispatcher must test ownership on the slot table");
assert.ok(!dispatcherSource.includes("activitySlot.hasOwnProperty(activitySlot)"),
    "dispatcher must not test ownership on a slot-name string");
assert.ok(farGrabSource.includes("if (manipulationPose && manipulationPose.valid)"),
    "off-hand rotation must be guarded by a current valid pose");
assert.ok(!farGrabSource.includes("Quat.multiply(pose.rotation"),
    "far grab must not consume the old unguarded pose variable");
assert.ok(!farGrabSource.includes("PICO4_FAR_GRAB update"),
    "far grab must not perform periodic diagnostic reads and logging");
assert.ok(farGrabSource.includes('traceFarGrabEdge("start"') &&
    farGrabSource.includes('traceFarGrabEdge("end"'),
    "far grab must retain opt-in edge-only start and end diagnostics");
assert.ok(!farGrabSource.includes("updatePicoLocalGrab") &&
    farDepthWorkerSource.includes("Script.update.connect(update)"),
    "local Pico per-frame work must run only in the independent worker engine");
assert.ok(farGrabSource.includes("if (!(picoUsesStickDepth && this.directLocalGrab))"),
    "the dispatcher must not duplicate local Pico far-grab transform updates");
assert.ok(farGrabSource.includes("this.releaseOnPicoInput"),
    "Pico far grab must expose immediate input-edge release");
assert.ok(farGrabSource.includes("this.picoLocalParentState") &&
    farGrabSource.includes("parentID: MyAvatar.SELF_ID") &&
    farGrabSource.includes("getControllerJointIndex(this.hand)"),
    "local Pico far grab must use the render-interpolated controller parent joint");
assert.ok(farGrabSource.includes("parentID: previousParentID || Uuid.NONE") &&
    farGrabSource.includes("position: releasedTransform.position"),
    "local Pico far-grab release must restore parenting without moving the entity");
assert.ok(farGrabSource.includes("parentEditNeeded") &&
    farGrabSource.includes("radiusDelta") &&
    !farGrabSource.includes("Overlays.addOverlay"),
    "Pico stick depth must retain the functional controller-parent offset path");
assert.ok(farGrabSource.includes("Entities.setLocalEntityPosition(this.targetEntityID"),
    "Pico local far-grab depth should use the packet-free local transform path");
assert.ok(farGrabSource.includes("Math.min(MAXIMUM_DEPTH_SPEED") &&
    farGrabSource.includes("Math.min(deltaObjectTime, MAXIMUM_DEPTH_STEP_SECONDS)") &&
    farGrabSource.includes("initialGrabRadius"),
    "Pico stick depth must bound frame gaps and derive position from its stable start anchor");
assert.ok(farGrabSource.includes("picoEdgeTraceEnabled && now - this.lastPicoDepthTrace >= 100") &&
    farGrabSource.includes("nativeUpdated: localPositionUpdated"),
    "Pico depth diagnostics must be opt-in, rate-limited, and report native update success");
assert.match(farGrabSource,
    /if \(!this\.directLocalGrab\) \{\s*var args = \[this\.hand[\s\S]*?continueDistanceGrab/,
    "the high-frequency local Pico transform path must not synchronously dispatch entity methods");
assert.ok(farGrabSource.includes('Script.load(Script.resolvePath("pico4FarGrabDepthWorker.js"))') &&
    farGrabSource.includes('this.sendPicoDepthCommand("start")') &&
    farGrabSource.includes('this.sendPicoDepthCommand("stop")') &&
    farGrabSource.includes('command.action === "ready"'),
    "local Pico grabs must manage the independent depth worker lifecycle");
assert.ok(farDepthWorkerSource.includes("Script.update.connect(update)") &&
    farDepthWorkerSource.includes("Entities.setLocalEntityPosition") &&
    farDepthWorkerSource.includes("Math.min(deltaTime, MAXIMUM_DEPTH_STEP_SECONDS)") &&
    farDepthWorkerSource.includes('source: "worker"'),
    "the Pico depth worker must integrate bounded local transforms and expose opt-in diagnostics");
assert.ok(dispatcherSource.includes('action: "configurePointers"') &&
    farDepthWorkerSource.includes('command.action === "configurePointers"') &&
    farDepthWorkerSource.includes("Pointers.setRenderState(pointerID, mode)") &&
    farDepthWorkerSource.includes("PICO_FAR_SELECT_ON_VALUE") &&
    farDepthWorkerSource.includes('mode = "hold"'),
    "the independent Pico worker must drive world-laser colors from shared thresholds and actual holds");
assert.ok(farGrabSource.indexOf('this.sendPicoDepthCommand("hold")') <
        farGrabSource.indexOf("Controller.triggerHapticPulse") &&
    farDepthWorkerSource.includes('command.action === "hold"') &&
    farDepthWorkerSource.includes("heldHands[hand] || trigger >= PICO_FAR_GRAB_ON_VALUE"),
    "the hold color must use the shared grab threshold immediately and retain confirmed-hold state");
assert.ok(farGrabSource.includes("this.tryStartPicoLocalGrab") &&
    farGrabSource.includes('targetProps.entityHostType !== "local"') &&
    farGrabSource.includes("var noEntityParent") &&
    dispatcherSource.includes("plugin.tryStartPicoLocalGrab(controllerData)"),
    "the trigger-edge path must fast-start only simple local Pico entities");
assert.ok(farGrabSource.indexOf('if (this.directLocalGrab)') <
        farGrabSource.indexOf('Entities.callEntityMethod(targetProps.id, "startDistanceGrab"'),
    "local parenting must not wait for a synchronous entity-script callback");
assert.ok(farGrabSource.includes("DEPTH_SPEED_MULTIPLIER = 3.0") &&
    farDepthWorkerSource.includes("DEPTH_SPEED_MULTIPLIER = 3.0"),
    "Pico depth control and its worker must share the validated threefold speed multiplier");
assert.ok(nearGrabSource.includes("PICO4_NEAR_GRAB"),
    "near grab must expose an opt-in dispatcher and MyAvatar timeline");
assert.ok(nearGrabSource.includes("localOnly"),
    "near-grab tracing must only accept local diagnostic control messages");
assert.ok(!stationSource.includes('Script.load(Script.resolvePath("pico4ObjectInteraction.js"))'),
    "the fixture station must not automatically load per-frame interaction diagnostics");
assert.ok(!stationSource.includes("Pico4-Interaction-Diagnostics"),
    "the fixture station must not automatically enable interaction tracing");
assert.match(applicationSource,
    /if \(!picoInteractionTestStationRequested &&\s*_picoServerlessSceneImportCommitted && _physicsEnabled\)/,
    "the Pico fixture station must load whenever the local acceptance scene is ready");
assert.doesNotMatch(applicationSource,
    /if \(picoTestMode && !picoInteractionTestStationRequested/,
    "the fixture station must not depend on the diagnostics property");
assert.ok(!stationSource.includes("picoWebEntityTest.js"),
    "the fixture station must not mix unrelated Web Entity tests into grab tests");
assert.ok(dispatcherSource.includes("PICO4_DISPATCHER"),
    "the dispatcher must expose an opt-in Grip-to-update timeline");
assert.ok(dispatcherSource.includes('picoTraceMode === "edges" && event === "trigger-mapping"'),
    "edge diagnostics must not log every analog trigger sample");
assert.ok(dispatcherSource.includes("picoDispatcherGap > 100"),
    "the dispatcher timeline must report long scheduling gaps");
assert.ok(dispatcherSource.includes('tracePicoDispatcher("update-duration"'),
    "the dispatcher timeline must attribute slow ticks to pipeline phases");
assert.ok(dispatcherSource.includes("entities: picoNearbyEnd - picoOverlaysEnd"),
    "the dispatcher timeline must separate overlay and entity lookup latency");
assert.ok(dispatcherSource.includes("picoLeftNearNeeded") &&
    dispatcherSource.includes("picoRightNearNeeded"),
    "Pico near searches must be restricted to hands with active interaction work");
assert.ok(dispatcherSource.includes("picoLeftModuleRunning") &&
    dispatcherSource.includes("picoRightModuleRunning"),
    "a running hand module must retain its hand's near-search data through release");
assert.ok(dispatcherSource.includes("picoIdlePointersDisabled"),
    "Pico idle polling must not repeat unchanged pointer-disable work");
assert.ok(dispatcherSource.includes("picoStickActive"),
    "the Pico idle fast path must wake for locomotion stick input");
assert.ok(dispatcherSource.includes("picoStickValues") &&
    dispatcherSource.includes(".to(_this.picoRightY)"),
    "Pico idle stick wake-up must use mapping callbacks instead of synchronous polling");
assert.ok(dispatcherSource.includes("picoOtherModuleRunning"),
    "the Pico idle fast path must retain modules without a hand-name prefix");
assert.ok(dispatcherSource.includes("picoKeepDispatcherActive") &&
    dispatcherSource.includes("picoLeftLocationNeeded"),
    "Pico stick activity must wake dispatch without forcing near-entity searches");
assert.ok(dispatcherSource.includes("releasePicoNearGrab") &&
    dispatcherSource.includes('tracePicoDispatcher("fast-release"'),
    "Pico Near Grab release must not wait behind the next entity-search tick");
assert.ok(dispatcherSource.includes("_this.pointerManager.lockPointerEnd(plugin.parameters.handLaser);") &&
    dispatcherSource.includes("_this.pointerManager.makePointerInvisible(plugin.parameters.handLaser)"),
    "Pico fast release must clear the held pointer lock and stale hold color");
assert.ok(dispatcherSource.includes("_this.leftTriggerValue >= PICO_TRIGGER_OFF_VALUE") &&
    dispatcherSource.includes("_this.rightTriggerValue >= PICO_TRIGGER_OFF_VALUE"),
    "Pico release must use the early analog trigger edge instead of synthesized click release");
assert.ok(dispatcherSource.includes("this.startPicoFarGrab") &&
    dispatcherSource.includes("Pointers.getPrevPickResult") &&
    dispatcherSource.includes('event: "far-fast-start"'),
    "Pico far grab must be able to start from the cached laser pick at the trigger edge");
assert.ok(dispatcherSource.includes("tracePicoTriggerBand") &&
    dispatcherSource.includes('event: "trigger-band"') &&
    pointersSource.includes('event: "render-state"') &&
    pointersSource.includes('event: "lock"') && pointersSource.includes('event: "unlock"'),
    "Pico laser diagnostics must record only threshold, color and lock state transitions");
assert.ok(dispatcherSource.includes("_this.pointerManager.updatePointersRenderState") &&
    pointersSource.includes("Pointers.setRenderState(this.pointerID, \"hold\")") &&
    pointersSource.includes("triggerValues[this.hand] > PICO_TRIGGER_OFF_VALUE"),
    "Pico laser colors must update directly from input with visible-state hysteresis");
assert.ok(dispatcherUtilsSource.includes(
    'readPicoInteractionThreshold("pico/interaction/farGrabOn", 0.90)'),
    "Pico far-grab intent must have one shared validated setting");
assert.ok(dispatcherSource.includes("value >= PICO_FAR_GRAB_ON_VALUE") &&
    farGrabSource.includes("picoUsesStickDepth ? PICO_FAR_SELECT_ON_VALUE") &&
    pointersSource.includes("PICO_FAR_SELECT_ON_VALUE") &&
    pointersSource.includes("PICO_LASER_ON_VALUE"),
    "Pico laser visibility, selection and grab must use their named shared thresholds");
[
    "pico/interaction/laserOn",
    "pico/interaction/farSelectOn",
    "pico/interaction/farGrabOn",
    "pico/interaction/triggerOff",
    "pico/interaction/gripOn",
    "pico/interaction/gripOff"
].forEach(key => {
    assert.ok(dispatcherUtilsSource.includes(key), "controller utilities must read " + key);
    assert.ok(picoInteractionSettingsSource.includes(key), "Pico settings UI must expose " + key);
});
assert.ok(dispatcherUtilsSource.includes("PICO_TRIGGER_OFF_VALUE >= PICO_LASER_ON_VALUE") &&
    dispatcherUtilsSource.includes("PICO_LASER_ON_VALUE >= PICO_FAR_SELECT_ON_VALUE") &&
    dispatcherUtilsSource.includes("PICO_FAR_SELECT_ON_VALUE >= PICO_FAR_GRAB_ON_VALUE") &&
    dispatcherUtilsSource.includes("PICO_GRIP_OFF_VALUE >= PICO_GRIP_ON_VALUE"),
    "Pico threshold settings must validate on/off hysteresis");
assert.ok(nearGrabSource.includes("releaseOnPicoInput") &&
    nearParentSource.includes("releaseOnPicoInput"),
    "both Near Grab implementations must expose the immediate Pico release hook");

let updateCallback;
let endingCallback;
const logs = [];
const values = Object.create(null);
const poses = {
    left: { valid: true, translation: { x: 0, y: 1, z: 0 } },
    right: { valid: true, translation: { x: 0, y: 1, z: 0 } }
};

global.Controller = {
    Standard: {
        LeftHand: "left", RightHand: "right",
        LT: "lt", RT: "rt", LTClick: "ltClick", RTClick: "rtClick",
        LeftGrip: "leftGrip", RightGrip: "rightGrip",
        LX: "lx", LY: "ly", RX: "rx", RY: "ry"
    },
    getPoseValue: input => poses[input],
    getValue: input => values[input] || 0
};
global.HMD = { mounted: true, isHandControllerAvailable: () => true };
global.MyAvatar = {};
let messageCallback;
global.Messages = {
    subscribe: () => {},
    unsubscribe: () => {},
    messageReceived: {
        connect: callback => { messageCallback = callback; },
        disconnect: callback => assert.strictEqual(callback, messageCallback)
    }
};
global.Script = {
    update: {
        connect: callback => { updateCallback = callback; },
        disconnect: callback => assert.strictEqual(callback, updateCallback)
    },
    scriptEnding: { connect: callback => { endingCallback = callback; } }
};
global.console = { info: message => logs.push(message) };

require(path.resolve(__dirname,
    "../../scripts/developer/debugging/pico4ObjectInteraction.js"));

assert.ok(updateCallback, "diagnostic must sample on Script.update");
updateCallback();
messageCallback("Hifi-Object-Manipulation", JSON.stringify({
    action: "grab", grabbedEntity: "fixture", joint: "LeftHand"
}), null, true);
values.lt = 0.96;
values.ltClick = 1;
updateCallback();
values.lt = 0;
values.ltClick = 0;
updateCallback();
poses.left = { valid: false, translation: { x: 0, y: 0, z: 0 } };
updateCallback();
poses.left = { valid: true, translation: { x: 0, y: 1, z: 0 } };
updateCallback();
endingCallback();

const summaryLine = logs.find(line => line.startsWith("PICO4_INTERACTION summary "));
assert.ok(summaryLine, "diagnostic must emit its final summary");
const summary = JSON.parse(summaryLine.slice("PICO4_INTERACTION summary ".length));
assert.strictEqual(summary.samples, 5);
assert.strictEqual(summary.triggerTransitions[0], 2);
assert.strictEqual(summary.triggerClickTransitions[0], 2);
assert.strictEqual(summary.trackingTransitions[0], 2);
assert.strictEqual(summary.invalidPose[0], 1);
assert.strictEqual(summary.manipulationEvents, 1);
assert.ok(logs.some(line => line === "PICO4_INTERACTION tracking left valid=false"));
assert.ok(logs.some(line => line === "PICO4_INTERACTION tracking left valid=true"));

process.stdout.write("PASS Pico interaction transition diagnostics\n");
