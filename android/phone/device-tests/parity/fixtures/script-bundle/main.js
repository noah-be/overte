// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Ordinary client script: real companion includes, local entity and tablet control.
Script.include(Script.resolvePath("nested/color.js"));
Script.include(Script.resolvePath("nested/shape.js"));
var phoneParityEntity = Entities.addEntity({
    type: PHONE_PARITY_SHAPE.type,
    name: "PHONE P2 companion cube",
    dimensions: PHONE_PARITY_SHAPE.dimensions,
    color: PHONE_PARITY_COLOR,
    position: Vec3.sum(MyAvatar.position, Vec3.multiply(2, Quat.getForward(MyAvatar.orientation)))
}, "local");
var phoneParityTablet = Tablet.getTablet("com.highfidelity.interface.tablet.system");
var phoneParityButton = phoneParityTablet.addButton({ text: "P2 SCRIPT" });
function phoneParityClick() {
    Entities.editEntity(phoneParityEntity, { color: { red: 255, green: 128, blue: 0 } });
}
phoneParityButton.clicked.connect(phoneParityClick);
Script.scriptEnding.connect(function () {
    phoneParityButton.clicked.disconnect(phoneParityClick);
    phoneParityTablet.removeButton(phoneParityButton);
    Entities.deleteEntity(phoneParityEntity);
});
