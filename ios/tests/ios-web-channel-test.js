// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Native transport boundary only; qwebchannel and Overte bootstrap are real.
"use strict";
const fs = require("fs");
const vm = require("vm");
const readline = require("readline");
const sandbox = {
    console: { log() {}, error: (...args) => process.stderr.write(args.join(" ") + "\n") },
    webkit: { messageHandlers: { overteWebChannel: {
        postMessage: message => {
            if (message.document !== "test-document") throw new Error("wrong document identity");
            process.stdout.write(message.envelope + "\n");
        }
    } } }
};
sandbox.window = sandbox;
vm.createContext(sandbox);
for (const source of process.argv.slice(2)) vm.runInContext(fs.readFileSync(source, "utf8"), sandbox);
sandbox.EventBridge.scriptEventReceived.connect(message => sandbox.EventBridge.emitWebEvent(message));
sandbox.EventBridge.emitWebEvent("queued before init");
readline.createInterface({ input: process.stdin }).on("line", data => {
    sandbox.qt.webChannelTransport.onmessage({ data });
});
