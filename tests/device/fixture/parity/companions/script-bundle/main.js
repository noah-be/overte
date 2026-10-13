// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Ordinary client script: real companion includes, local entity and tablet control.
Script.include(Script.resolvePath("nested/color.js"));
Script.include(Script.resolvePath("nested/shape.js"));
var sharedParityEntity = Entities.addEntity({
    type: SHARED_PARITY_SHAPE.type,
    name: "PARITY companion cube",
    dimensions: SHARED_PARITY_SHAPE.dimensions,
    color: SHARED_PARITY_COLOR,
    position: Vec3.sum(MyAvatar.position, Vec3.multiply(2, Quat.getForward(MyAvatar.orientation)))
}, "local");
var sharedParityTablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
var sharedParityButton = sharedParityTablet.addButton({ text: "P2 SCRIPT" });
function sharedParityClick() {
    Entities.editEntity(sharedParityEntity, { color: { red: 255, green: 128, blue: 0 } });
}
sharedParityButton.clicked.connect(sharedParityClick);
Script.scriptEnding.connect(function () {
    sharedParityButton.clicked.disconnect(sharedParityClick);
    sharedParityTablet.removeButton(sharedParityButton);
    Entities.deleteEntity(sharedParityEntity);
});
