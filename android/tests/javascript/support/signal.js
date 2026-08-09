"use strict";

class FakeSignal {
    #listeners = [];

    connect(listener) {
        if (typeof listener !== "function") {
            throw new TypeError("signal listener must be a function");
        }
        if (!this.#listeners.includes(listener)) {
            this.#listeners.push(listener);
        }
    }

    disconnect(listener) {
        this.#listeners = this.#listeners.filter((candidate) => candidate !== listener);
    }

    emit(...args) {
        // Copy first: listeners may safely connect or disconnect during delivery.
        for (const listener of [...this.#listeners]) {
            listener(...args);
        }
    }

    get listenerCount() {
        return this.#listeners.length;
    }
}

module.exports = { FakeSignal };
