"use strict";

const { FakeSignal } = require("./signal");

const loaders = new WeakMap();

function bindScriptLoader(api, loader) {
    const state = loaders.get(api);
    if (state) {
        state.loader = loader;
    } else if (api) {
        api.include = loader.include;
        if (typeof api.resolvePath !== "function") {
            api.resolvePath = loader.resolvePath;
        }
    }
}

function createScriptApi() {
    const state = { loader: null };
    let nextTimerId = 1;
    const timers = new Map();
    const clearedTimers = [];

    function schedule(callback, delay, repeating) {
        if (typeof callback !== "function") {
            throw new TypeError("timer callback must be a function");
        }
        const id = nextTimerId++;
        timers.set(id, { callback, delay, repeating });
        return id;
    }

    function clear(id) {
        if (timers.delete(id)) {
            clearedTimers.push(id);
        }
    }

    const api = {
        scriptEnding: new FakeSignal(),
        setTimeout(callback, delay = 0) {
            return schedule(callback, delay, false);
        },
        clearTimeout: clear,
        setInterval(callback, delay = 0) {
            return schedule(callback, delay, true);
        },
        clearInterval: clear,
        resolvePath(path) {
            return state.loader ? state.loader.resolvePath(path) : path;
        },
        include(files, callback) {
            if (!state.loader) {
                throw new Error("Script.include requires a production VM loader");
            }
            return state.loader.include(files, callback);
        },
        runTimer(id) {
            const timer = timers.get(id);
            if (!timer) {
                return false;
            }
            if (!timer.repeating) {
                timers.delete(id);
            }
            timer.callback();
            return true;
        },
        end() {
            this.scriptEnding.emit();
        },
        timers,
        clearedTimers
    };
    loaders.set(api, state);
    return api;
}

module.exports = { createScriptApi, bindScriptLoader };
