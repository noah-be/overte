// Device-free source contracts for Pico tablet lifecycle and local messages.
// SPDX-License-Identifier: Apache-2.0

"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../scripts/system/tablet-ui/tabletUI.js"), "utf8");

assert.ok(source.includes("if (!localOnly || senderUUID !== MyAvatar.sessionUUID)"),
    "tablet control messages must be local and self-authored");
assert.ok(source.includes("try {\n                requestedHand = JSON.parse(hand)"),
    "toggleHand parsing must be guarded");
assert.ok(source.includes("requestedHand !== controllerStandard.LeftHand"));
assert.ok(source.includes("requestedHand !== controllerStandard.RightHand"));

assert.ok(source.includes("Script.clearInterval(updateShowTabletTimer)"));
assert.ok(source.includes("Messages.messageReceived.disconnect(handleMessage)"));
for (const channel of ["toggleHand", "home", "Pico-Tablet-Move-Aside-For-Create"]) {
    assert.ok(source.includes(`Messages.unsubscribe("${channel}")`),
        `cleanup must unsubscribe ${channel}`);
}
assert.ok(source.includes("clickMapping.disable()"));

process.stdout.write("PASS Pico tablet lifecycle contracts\n");
