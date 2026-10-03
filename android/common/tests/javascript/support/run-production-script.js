"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { fileURLToPath } = require("node:url");
const { bindScriptLoader } = require("./script");

function runProductionScript(filename, globals) {
    const entry = fs.realpathSync(filename);
    const context = vm.createContext({ ...globals });
    const loadedFiles = [];
    const included = new Set();
    const frames = [];
    // Substitute only the exact target, including when a wrapper includes it.
    // VM filenames retain the production identity for coverage and diagnostics.
    const mutationTarget = process.env.OVERTE_MUTATION_TARGET;
    const mutationSource = process.env.OVERTE_MUTATION_SOURCE;
    if (Boolean(mutationTarget) !== Boolean(mutationSource)) {
        throw new Error("mutation target and source must be supplied together");
    }
    const target = mutationTarget ? fs.realpathSync(mutationTarget) : null;

    function resolvePath(value) {
        if (value.startsWith("file:")) {
            return fileURLToPath(value);
        }
        if (/^[a-z][a-z0-9+.-]*:/i.test(value)) {
            throw new Error("network script loading is outside the local fixture");
        }
        // VM callbacks retain their defining filename after initial evaluation.
        // Resolve against the nearest known production frame, including callbacks
        // defined in an include and later invoked by a host Signal or timer.
        const stack = new Error().stack.split("\n");
        const caller = stack.flatMap((frame) =>
            loadedFiles.filter((file) => frame.includes(file + ":")))[0];
        return path.resolve(path.dirname(caller || frames.at(-1) || entry), value);
    }

    function evaluate(file) {
        const actual = fs.realpathSync(resolvePath(file));
        const source = fs.readFileSync(actual === target ? mutationSource : actual, "utf8");
        frames.push(actual);
        loadedFiles.push(actual);
        try {
            return vm.runInContext(source, context, { filename: actual, timeout: 1000 });
        } finally {
            frames.pop();
        }
    }

    function include(files, callback) {
        if (callback != null && typeof callback !== "function") {
            throw new TypeError("include callback must be a function");
        }
        for (const file of Array.isArray(files) ? files : [files]) {
            const actual = fs.realpathSync(resolvePath(file));
            if (!included.has(actual)) {
                included.add(actual);
                evaluate(actual);
            }
        }
        // The local fixture has no downloader/event loop: callback scheduling
        // uses the deterministic Script timer instead of claiming network parity.
        if (callback) {
            context.Script.setTimeout(callback, 0);
        }
    }

    bindScriptLoader(context.Script, { include, resolvePath });
    const result = evaluate(entry);
    return { context, result, loadedFiles };
}

module.exports = { runProductionScript };
