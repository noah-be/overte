"use strict";

const fs = require("node:fs");
const vm = require("node:vm");

function runProductionScript(filename, globals) {
    // The mutation harness can substitute one exact production file while all
    // ordinary tests continue to read the repository path directly.
    const mutationTarget = process.env.OVERTE_MUTATION_TARGET;
    const mutationSource = process.env.OVERTE_MUTATION_SOURCE;
    const selectedFilename = mutationTarget && mutationSource
        && fs.realpathSync(filename) === fs.realpathSync(mutationTarget)
        ? mutationSource : filename;
    const source = fs.readFileSync(selectedFilename, "utf8");
    const context = vm.createContext({ ...globals });
    const result = vm.runInContext(source, context, { filename, timeout: 1000 });
    return { context, result };
}

module.exports = { runProductionScript };
