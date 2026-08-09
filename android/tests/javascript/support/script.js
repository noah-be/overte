"use strict";

const { FakeSignal } = require("./signal");

function createScriptApi() {
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

    return {
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
            return path;
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
}

module.exports = { createScriptApi };
