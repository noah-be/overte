//
//  pico4InteractionTestStation.js
//
//  Local near/far grab fixtures for Pico 4 controller testing.
//  SPDX-License-Identifier: Apache-2.0
//

/* global Entities, MyAvatar, Quat, Script, Selection, Vec3, console */

"use strict";

var LIFETIME_SECONDS = 60 * 60;
var fixtureIDs = [];
var avatarYaw = Quat.fromPitchYawRollDegrees(0, Quat.safeEulerAngles(MyAvatar.orientation).y, 0);

// Developer render tools use these global selection names and can leave a
// head-directed outline in VR. They are unrelated to controller grab feedback
// and must not contaminate Pico interaction tests.
["DebugWorkloadSelection", "Hovering"].forEach(function (selectionName) {
    Selection.clearSelectedItemsList(selectionName);
    Selection.disableListHighlight(selectionName);
    Selection.removeListFromMap(selectionName);
});
console.info("PICO4_INTERACTION_TEST_STATION cleared developer hover highlights");

function worldOffset(offset) {
    return Vec3.sum(MyAvatar.position, Vec3.multiplyQbyV(avatarYaw, offset));
}

function addFixture(properties) {
    properties.lifetime = LIFETIME_SECONDS;
    fixtureIDs.push(Entities.addEntity(properties, "local"));
}

function grabbableData(label) {
    return JSON.stringify({
        grabbableKey: {
            grabbable: true,
            kinematic: false
        },
        pico4InteractionTest: label
    });
}

addFixture({
    name: "Pico 4 interaction test platform",
    type: "Box",
    position: worldOffset({ x: 2.0, y: 0.75, z: -1.05 }),
    rotation: avatarYaw,
    dimensions: { x: 1.6, y: 0.08, z: 1.5 },
    color: { red: 55, green: 55, blue: 60 },
    shape: "Cube",
    shapeType: "box",
    dynamic: false,
    userData: JSON.stringify({ grabbableKey: { grabbable: false } })
});

addFixture({
    name: "Pico 4 NEAR GRAB red cube",
    type: "Box",
    position: worldOffset({ x: 1.68, y: 1.02, z: -0.62 }),
    rotation: avatarYaw,
    dimensions: { x: 0.22, y: 0.22, z: 0.22 },
    color: { red: 235, green: 45, blue: 45 },
    shape: "Cube",
    shapeType: "box",
    dynamic: true,
    gravity: { x: 0, y: 0, z: 0 },
    damping: 0.5,
    angularDamping: 0.5,
    userData: grabbableData("near-left")
});

addFixture({
    name: "Pico 4 FAR GRAB blue cube",
    type: "Box",
    position: worldOffset({ x: 2.35, y: 1.12, z: -1.45 }),
    rotation: avatarYaw,
    dimensions: { x: 0.32, y: 0.32, z: 0.32 },
    color: { red: 35, green: 105, blue: 245 },
    shape: "Cube",
    shapeType: "box",
    dynamic: true,
    gravity: { x: 0, y: 0, z: 0 },
    damping: 0.5,
    angularDamping: 0.5,
    userData: grabbableData("far-right")
});

addFixture({
    name: "Pico 4 NOT GRABBABLE control cube",
    type: "Box",
    position: worldOffset({ x: 2.0, y: 1.02, z: -0.95 }),
    rotation: avatarYaw,
    dimensions: { x: 0.18, y: 0.18, z: 0.18 },
    color: { red: 235, green: 210, blue: 35 },
    shape: "Cube",
    shapeType: "box",
    dynamic: false,
    userData: JSON.stringify({
        grabbableKey: { grabbable: false },
        pico4InteractionTest: "negative-control"
    })
});

console.info("PICO4_INTERACTION_TEST_STATION ready fixtures=" + JSON.stringify(fixtureIDs));

Script.scriptEnding.connect(function () {
    fixtureIDs.forEach(function (id) {
        Entities.deleteEntity(id);
    });
    console.info("PICO4_INTERACTION_TEST_STATION removed");
});
