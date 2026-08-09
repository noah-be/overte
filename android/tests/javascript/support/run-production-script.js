"use strict";

const fs = require("node:fs");
const vm = require("node:vm");

function runProductionScript(filename, globals) {
    const source = fs.readFileSync(filename, "utf8");
    const context = vm.createContext({ ...globals });
    const result = vm.runInContext(source, context, { filename, timeout: 1000 });
    return { context, result };
}

module.exports = { runProductionScript };
