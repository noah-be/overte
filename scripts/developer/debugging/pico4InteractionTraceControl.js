// Enable lightweight, transition-only Pico interaction diagnostics while this
// script is running. Load and stop it explicitly from the Running Scripts UI.
// SPDX-License-Identifier: Apache-2.0

/* global Messages, Script */

"use strict";

var TRACE_CHANNEL = "Pico4-Interaction-Diagnostics";
function enableTrace() {
    Messages.sendLocalMessage(TRACE_CHANNEL, "edges");
}

enableTrace();
Script.setTimeout(enableTrace, 250);
Script.setTimeout(enableTrace, 1000);
var keepAlive = Script.setInterval(enableTrace, 5000);

Script.scriptEnding.connect(function () {
    Script.clearInterval(keepAlive);
    Messages.sendLocalMessage(TRACE_CHANNEL, "disable");
});
